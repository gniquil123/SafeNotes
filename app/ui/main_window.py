"""主窗口：三栏布局 + 顶栏 + 撤销/重做 + 安全增强（自动锁定 / 剪贴板 / 防截屏）。"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QToolButton, QVBoxLayout, QWidget,
)

from app.core.clipboard import ClipboardManager
from app.core.commands import (
    CreateEntryCommand, PurgeCommand, SaveEntryCommand,
    SoftDeleteCommand, UndeleteCommand,
)
from app.core.database import Database
from app.core.models import Entry, now_iso
from app.core.undostack import UndoManager
from app.crypto.vault import SessionVault, change_password, rotate_backups
from app.ui.entry_editor import EntryEditor
from app.ui.history_dialog import HistoryDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.style import build_qss
from app.utils.win32 import enable_anti_capture


def toast(parent, msg, msec=2600):
    parent.statusBar().showMessage(msg, msec)


class _GlobalFilter(QObject):
    """应用级事件过滤：活动监听 + Ctrl+V 图片粘贴捕获。"""

    def __init__(self, touch_cb, paste_cb, parent=None):
        super().__init__(parent)
        self._touch = touch_cb
        self._paste = paste_cb

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.MouseMove, QEvent.MouseButtonPress,
                 QEvent.KeyPress, QEvent.Wheel, QEvent.TouchBegin):
            self._touch()
        if t == QEvent.KeyPress and ev.key() == Qt.Key_V and (ev.modifiers() & Qt.ControlModifier):
            if self._paste():
                return True
        return False


def entry_share_text(e: Entry) -> str:
    """把条目整理成便于粘贴发送给别人的纯文本。"""
    lines = [f"【{e.title or '未命名'}】"]
    if e.type == "password":
        if e.fields.get("username"):
            lines.append(f"账号：{e.fields['username']}")
        if e.fields.get("password"):
            lines.append(f"密码：{e.fields['password']}")
        if e.fields.get("url"):
            lines.append(f"网址：{e.fields['url']}")
        if e.fields.get("notes"):
            lines.append(f"备注：{e.fields['notes']}")
    else:
        if e.fields.get("content"):
            lines.append(e.fields["content"])
    if e.images:
        lines.append(f"（另有 {len(e.images)} 张图片，请从应用内查看）")
    return "\n".join(lines)


class MainWindow(QMainWindow):
    locked = Signal()

    def __init__(self, vault: SessionVault, db_dict: dict, parent=None):
        super().__init__(parent)
        self.vault = vault
        self.db = Database.from_dict(db_dict)
        self.undo_mgr = UndoManager()
        self.undo_mgr.on_change = self._refresh_undo_buttons
        self.clip = ClipboardManager(self)
        self.view = {"cat": "all", "search": "", "sel": None}
        self._session_saved = False
        self._last_activity = time.time()

        self.setWindowTitle("加密记事本")
        self.resize(1180, 720)
        self._build_ui()

        self._activity_filter = _GlobalFilter(self._touch, self._handle_paste)
        QApplication.instance().installEventFilter(self._activity_filter)

        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start(1000)

        self.render_all()

    # ================= UI 构建 =================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 顶栏 ----
        top = QWidget()
        top.setObjectName("topbar")
        top.setFixedHeight(52)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(14, 6, 14, 6)
        tl.setSpacing(8)
        icon = QLabel("🔐")
        icon.setObjectName("brandIcon")
        tl.addWidget(icon)
        brand = QLabel("加密记事本")
        brand.setObjectName("brand")
        tl.addWidget(brand)
        tl.addSpacing(6)

        self.btn_undo = QToolButton()
        self.btn_undo.setText("↩")
        self.btn_undo.setToolTip("撤销 (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.do_undo)
        self.btn_redo = QToolButton()
        self.btn_redo.setText("↪")
        self.btn_redo.setToolTip("重做 (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.do_redo)
        tl.addWidget(self.btn_undo)
        tl.addWidget(self.btn_redo)
        tl.addStretch(1)

        b_new_pw = QPushButton("＋ 密码条目")
        b_new_pw.clicked.connect(lambda: self.start_draft("password"))
        tl.addWidget(b_new_pw)
        b_new_note = QPushButton("＋ 笔记")
        b_new_note.clicked.connect(lambda: self.start_draft("note"))
        tl.addWidget(b_new_note)

        b_lock = QToolButton()
        b_lock.setText("🔒")
        b_lock.setToolTip("立即锁定（清除内存中的密钥与明文）")
        b_lock.clicked.connect(lambda: self.lock("已手动锁定"))
        tl.addWidget(b_lock)
        self.btn_theme = QToolButton()
        self.btn_theme.setText("🌗")
        self.btn_theme.setToolTip("切换浅色 / 深色主题")
        self.btn_theme.clicked.connect(self.toggle_theme)
        tl.addWidget(self.btn_theme)
        b_set = QToolButton()
        b_set.setText("⚙️")
        b_set.setToolTip("设置")
        b_set.clicked.connect(self.open_settings)
        tl.addWidget(b_set)
        root.addWidget(top)

        # ---- 三栏 ----
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        split.setChildrenCollapsible(False)

        # 侧栏
        side = QWidget()
        side.setObjectName("sidePanel")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 10, 10, 10)
        sv.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索标题 / 账号 / 内容…")
        self.search_edit.textChanged.connect(self._on_search)
        sv.addWidget(self.search_edit)
        self.cat_list = QListWidget()
        self.cat_list.setObjectName("catList")
        self.cat_list.itemClicked.connect(self._on_cat_clicked)
        sv.addWidget(self.cat_list, 1)
        b_addcat = QPushButton("📁 ＋ 新建分类")
        b_addcat.setProperty("flat", True)
        b_addcat.clicked.connect(self._add_category)
        sv.addWidget(b_addcat)
        split.addWidget(side)

        # 条目列表
        listp = QWidget()
        listp.setObjectName("listPanel")
        listp.setFixedWidth(300)
        lv = QVBoxLayout(listp)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        head_row = QWidget()
        hr = QHBoxLayout(head_row)
        hr.setContentsMargins(16, 12, 16, 12)
        self.list_head = QLabel("全部条目")
        self.list_head.setObjectName("listHead")
        hr.addWidget(self.list_head)
        hr.addStretch(1)
        self.btn_empty_trash = QPushButton("🧹 清空回收站")
        self.btn_empty_trash.setProperty("danger", True)
        self.btn_empty_trash.setFixedHeight(26)
        self.btn_empty_trash.clicked.connect(self.on_empty_trash)
        self.btn_empty_trash.hide()
        hr.addWidget(self.btn_empty_trash)
        lv.addWidget(head_row)
        self.entry_list = QListWidget()
        self.entry_list.setObjectName("entryList")
        self.entry_list.itemClicked.connect(self._on_entry_clicked)
        lv.addWidget(self.entry_list, 1)
        split.addWidget(listp)

        # 详情
        self.editor = EntryEditor(clip_sec_getter=lambda: self.db.settings.get("clip_sec", 20))
        self.editor.save_requested.connect(self.on_save_form)
        self.editor.cancel_requested.connect(self.on_cancel_edit)
        self.editor.delete_requested.connect(self.on_delete_entry)
        self.editor.duplicate_requested.connect(self.on_duplicate_entry)
        self.editor.share_requested.connect(self.on_share_entry)
        self.editor.history_requested.connect(self.on_history)
        self.editor.copy_secret.connect(self.on_copy_secret)
        split.addWidget(self.editor)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 0)
        split.setStretchFactor(2, 1)
        split.setSizes([210, 300, 670])
        root.addWidget(split, 1)

        self.statusBar().showMessage(
            f"🔒 {self.vault.path} ｜ Argon2id + AES-256-GCM 加密存储 ｜ 防截屏已启用"
            if enable_anti_capture(self) else f"🔒 {self.vault.path} ｜ Argon2id + AES-256-GCM 加密存储")

        # 快捷键
        self._act_save = QAction(self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self._shortcut_save)
        self.addAction(self._act_save)
        self._act_undo = QAction(self)
        self._act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self._act_undo.triggered.connect(self._shortcut_undo)
        self.addAction(self._act_undo)
        self._act_redo = QAction(self)
        self._act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self._act_redo.triggered.connect(self.do_redo)
        self.addAction(self._act_redo)

    # ================= 渲染 =================
    def render_all(self):
        self.render_sidebar()
        self.render_list()
        self.render_detail()

    def render_sidebar(self):
        total, per, trash = self.db.counts()
        self.cat_list.blockSignals(True)
        self.cat_list.clear()
        self.cat_list.addItem(self._cat_item("all", "📋", "全部条目", total))
        for c in self.db.categories():
            self.cat_list.addItem(self._cat_item(c, "📁", c, per.get(c, 0)))
        self.cat_list.addItem(self._cat_item("trash", "🗑️", "回收站", trash))
        cur = self.view["cat"]
        for i in range(self.cat_list.count()):
            if self.cat_list.item(i).data(Qt.UserRole) == cur:
                self.cat_list.setCurrentRow(i)
                break
        self.cat_list.blockSignals(False)

    @staticmethod
    def _cat_item(key: str, icon: str, name: str, count: int) -> QListWidgetItem:
        it = QListWidgetItem(f"{icon}  {name}　{count}")
        it.setData(Qt.UserRole, key)
        return it

    def render_list(self):
        cat = self.view["cat"]
        entries = self.db.visible(cat, self.view["search"])
        name = {"all": "全部条目", "trash": "回收站"}.get(cat, cat)
        self.list_head.setText(f"{name}（{len(entries)}）")
        self.btn_empty_trash.setVisible(cat == "trash" and bool(entries))
        self.entry_list.blockSignals(True)
        self.entry_list.clear()
        sel = self.view.get("sel")
        for e in entries:
            icon = "🗑️" if e.deleted else ("🔑" if e.type == "password" else "📝")
            if e.deleted:
                sub = f"删除于 {(e.deleted_at or '').replace('T', ' ')[:16]}"
            elif e.type == "password":
                sub = e.fields.get("username") or e.fields.get("url") or "（无账号）"
            else:
                c = (e.fields.get("content") or "").replace("\n", " ").strip()
                sub = c[:40] or "（空笔记）"
            it = QListWidgetItem(f"{icon}  {e.title or '（未命名）'}\n     {sub}")
            it.setData(Qt.UserRole, e.id)
            self.entry_list.addItem(it)
            if sel and sel.get("id") == e.id:
                self.entry_list.setCurrentItem(it)
        self.entry_list.blockSignals(False)

    def render_detail(self):
        sel = self.view.get("sel")
        if not sel:
            self.editor._load_empty()
            return
        if sel.get("draft"):
            self.editor.load_draft(sel["type"], self.db.categories(),
                                   category=sel.get("category", ""))
            return
        e = self.db.get(sel.get("id"))
        if e is None:
            self.editor._load_empty()
            return
        if e.deleted:
            self._render_trash_view(e)
        else:
            self.editor.load_entry(e, self.db.categories())

    def _render_trash_view(self, e: Entry):
        from PySide6.QtWidgets import QFrame, QFormLayout
        w = QWidget()
        card = QFrame()
        card.setProperty("card", True)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        outer.addStretch(1)
        form = QFormLayout(card)
        form.setContentsMargins(20, 16, 20, 16)
        form.addRow("状态", QLabel(f"🗑️ 回收站 · {'密码条目' if e.type == 'password' else '笔记'}"))
        form.addRow("标题", QLabel(e.title or "（未命名）"))
        form.addRow("分类", QLabel(e.category))
        form.addRow("删除时间", QLabel((e.deleted_at or "").replace("T", " ")[:16]))
        if e.type == "password":
            form.addRow("账号", QLabel(e.fields.get("username") or "—"))
            form.addRow("网址", QLabel(e.fields.get("url") or "—"))
        else:
            lbl = QLabel((e.fields.get("content") or "—")[:400])
            lbl.setWordWrap(True)
            form.addRow("内容", lbl)
        form.addRow("历史版本", QLabel(f"{len(e.history)} 份（恢复条目后可用）"))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 8, 0, 0)
        b_restore = QPushButton("↩ 恢复此条目")
        b_restore.setProperty("primary", True)
        b_restore.clicked.connect(lambda: self.on_restore_entry(e.id))
        h.addWidget(b_restore)
        b_purge = QPushButton("✕ 彻底删除")
        b_purge.setProperty("danger", True)
        b_purge.clicked.connect(lambda: self.on_purge_entry(e.id))
        h.addWidget(b_purge)
        h.addStretch(1)
        form.addRow("", row)
        self.editor.scroll.setWidget(w)

    # ================= 交互：导航 =================
    def _guard_dirty(self) -> bool:
        if self.editor.is_dirty():
            r = QMessageBox.question(
                self, "未保存的修改",
                "当前条目有未保存的修改，确定放弃吗？\n"
                "（未保存的内容将丢失，已保存的历史版本不受影响）",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return r == QMessageBox.Yes
        return True

    def _on_cat_clicked(self, item):
        if not self._guard_dirty():
            self.render_sidebar()
            return
        self.view["cat"] = item.data(Qt.UserRole)
        self.view["sel"] = None
        self.render_sidebar()
        self.render_list()
        self.render_detail()

    def _on_entry_clicked(self, item):
        eid = item.data(Qt.UserRole)
        if self.view.get("sel") and self.view["sel"].get("id") == eid:
            return
        if not self._guard_dirty():
            self.render_list()
            return
        self.view["sel"] = {"id": eid}
        self.render_detail()

    def _on_search(self, text):
        self.view["search"] = text
        self.render_list()

    def _add_category(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建分类", "分类名称：")
        if ok and name.strip():
            self.start_draft("password", category=name.strip())

    def start_draft(self, entry_type: str, category: str = ""):
        if not self._guard_dirty():
            return
        self.view["sel"] = {"draft": True, "type": entry_type, "category": category}
        self.render_detail()

    # ================= 业务操作 =================
    def _after_change(self):
        self.persist()
        self.render_all()

    def on_save_form(self, ne: Entry):
        sel = self.view.get("sel")
        if not sel:
            return
        if sel.get("draft"):
            self.db.insert(ne)
            self.undo_mgr.push(CreateEntryCommand(self.db, ne))
            self.view["sel"] = {"id": ne.id}
            toast(self, "已加密保存新条目 ✔")
        else:
            cur = self.db.get(sel["id"])
            if cur is None:
                return
            old = cur.deep_copy()
            ne.history = self.db.push_history(cur, "编辑保存")
            ne.updated_at = now_iso()
            self.db.replace(ne)
            self.undo_mgr.push(SaveEntryCommand(self.db, old, ne))
            toast(self, "已加密保存（旧版本已存入历史）✔")
        self._after_change()

    def on_cancel_edit(self):
        self.render_detail()

    def on_delete_entry(self):
        sel = self.view.get("sel")
        if not sel or not sel.get("id"):
            return
        e = self.db.get(sel["id"])
        if not e:
            return
        r = QMessageBox.question(
            self, "移入回收站",
            f"将「{e.title or '未命名'}」移入回收站？\n"
            "（可从回收站恢复，Ctrl+Z 也可直接撤销）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r != QMessageBox.Yes:
            return
        self.db.soft_delete(e.id)
        self.undo_mgr.push(SoftDeleteCommand(self.db, e.id, e.title))
        self.view["sel"] = None
        self._after_change()

    def on_restore_entry(self, eid: str):
        e = self.db.get(eid)
        if not e:
            return
        self.db.undelete(eid)
        self.undo_mgr.push(UndeleteCommand(self.db, eid, e.title))
        toast(self, "已恢复到原分类 ✔")
        self._after_change()

    def on_purge_entry(self, eid: str):
        e = self.db.get(eid)
        if not e:
            return
        r = QMessageBox.warning(
            self, "彻底删除",
            f"彻底删除「{e.title or '未命名'}」？\n"
            f"该条目及其 {len(e.history)} 份历史版本将被永久移除。\n"
            "（本次会话内仍可用 Ctrl+Z 撤销此操作）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.undo_mgr.push(PurgeCommand(self.db, [eid], "彻底删除条目"))
        self._after_change()

    def on_empty_trash(self):
        ids = [e.id for e in self.db.entries if e.deleted]
        if not ids:
            return
        r = QMessageBox.warning(
            self, "清空回收站",
            f"清空回收站？共 {len(ids)} 个条目将被永久移除（含其全部历史版本）。\n"
            "（本次会话内仍可用 Ctrl+Z 撤销此操作）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.undo_mgr.push(PurgeCommand(self.db, ids, f"清空回收站（{len(ids)} 项）"))
        self._after_change()

    def on_duplicate_entry(self):
        """以当前条目为模板新建草稿（保留分类/账号/密码/内容/图片）。"""
        sel = self.view.get("sel")
        if not sel or not sel.get("id"):
            return
        e = self.db.get(sel["id"])
        if e is None or e.deleted:
            return
        if not self._guard_dirty():
            return
        self.view["sel"] = {"draft": True, "type": e.type}
        self.editor.load_duplicate(e, self.db.categories())

    def on_share_entry(self):
        """把当前条目的文本内容复制到剪贴板（走同一套定时清除）。"""
        sel = self.view.get("sel")
        e = self.db.get(sel["id"]) if sel and sel.get("id") else None
        if e is None:
            toast(self, "没有可分享的条目")
            return
        self.on_copy_secret(entry_share_text(e))

    def on_history(self):
        sel = self.view.get("sel")
        if not sel or not sel.get("id"):
            return
        e = self.db.get(sel["id"])
        if not e:
            return
        dlg = HistoryDialog(e, self)
        dlg.restore_requested.connect(lambda idx: self.on_restore_history(sel["id"], idx))
        dlg.exec()

    def on_restore_history(self, eid: str, hist_index: int):
        cur = self.db.get(eid)
        ne = self.db.restore_history(eid, hist_index)
        if ne is None:
            return
        old = cur.deep_copy()
        total = len(cur.history)
        ver_no = total - hist_index
        self.db.replace(ne)
        self.undo_mgr.push(SaveEntryCommand(self.db, old, ne,
                                            label=f"恢复第 {ver_no} 版「{ne.title or '未命名'}」"))
        toast(self, f"已恢复第 {ver_no} 版 ✔（恢复前已自动快照）")
        self._after_change()

    def on_copy_secret(self, text: str):
        if not text:
            toast(self, "没有可复制的内容")
            return
        sec = self.db.settings.get("clip_sec", 20)
        self.clip.copy_secret(
            text, sec,
            on_cleared=lambda: toast(self, "剪贴板已自动清除"),
            on_skip=lambda: toast(self, "剪贴板内容已变化，跳过清除"))
        toast(self, f"已复制，{sec} 秒后自动清除" if sec else "已复制（未启用自动清除）")

    # ================= 撤销 / 重做 =================
    def do_undo(self):
        if not self.undo_mgr.can_undo:
            return
        if not self._guard_dirty():
            return
        label = self.undo_mgr.undo()
        self._after_change()
        if label:
            toast(self, f"已撤销：{label}")

    def do_redo(self):
        if not self.undo_mgr.can_redo:
            return
        if not self._guard_dirty():
            return
        label = self.undo_mgr.redo()
        self._after_change()
        if label:
            toast(self, f"已重做：{label}")

    def _refresh_undo_buttons(self):
        self.btn_undo.setEnabled(self.undo_mgr.can_undo)
        self.btn_redo.setEnabled(self.undo_mgr.can_redo)
        if self.undo_mgr.undo_label:
            self.btn_undo.setToolTip(f"撤销 (Ctrl+Z)：{self.undo_mgr.undo_label}")
        if self.undo_mgr.redo_label:
            self.btn_redo.setToolTip(f"重做 (Ctrl+Y)：{self.undo_mgr.redo_label}")

    def _shortcut_save(self):
        if self.view.get("sel") and not self.editor.is_empty():
            self.editor._on_save()

    def _shortcut_undo(self):
        # 输入框内 Ctrl+Z → 文本级撤销；输入框外 → 条目级撤销（与 demo 一致）
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit,)) or type(w).__name__ in ("QPlainTextEdit", "QTextEdit"):
            return
        self.do_undo()

    # ================= 持久化 / 设置 / 主题 =================
    def persist(self):
        if not self.vault or not self.vault.key.is_valid:
            return
        if not self._session_saved:
            rotate_backups(self.vault.path)      # 会话首次保存前留一份滚动备份
            self._session_saved = True
        self.vault.save(self.db.to_dict())

    def apply_theme(self, theme: str):
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_qss(theme))

    def toggle_theme(self):
        t = "dark" if self.db.settings.get("theme", "light") == "light" else "light"
        self.db.settings["theme"] = t
        self.apply_theme(t)
        self.persist()

    def open_settings(self):
        dlg = SettingsDialog(self.db.settings, self)
        dlg.apply_requested.connect(self._apply_settings)
        dlg.change_password_requested.connect(self._change_password)
        dlg.export_backup_requested.connect(self._export_backup)
        dlg.exec()

    def _apply_settings(self, s: dict):
        self.db.settings.update(s)
        self.apply_theme(s.get("theme", "light"))
        self.persist()
        toast(self, "设置已保存（随保险库加密存储）✔")

    def _change_password(self, old_pw: str, new_pw: str):
        try:
            self.persist()          # 先落当前数据
            new_vault = change_password(self.vault.path, old_pw, new_pw, None)
        except Exception as e:       # noqa: BLE001
            QMessageBox.critical(self, "修改失败", str(e))
            return
        self.vault.wipe()
        self.vault = new_vault
        self._session_saved = True
        toast(self, "主密码已修改，全部数据已用新密码重新加密 ✔（已自动备份）")

    def _export_backup(self):
        default = time.strftime("加密记事本备份_%Y%m%d_%H%M%S.vault")
        target, _ = QFileDialog.getSaveFileName(self, "导出加密备份", default,
                                                "加密保险库 (*.vault)")
        if not target:
            return
        self.persist()
        try:
            shutil.copy2(self.vault.path, target)
        except OSError as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(
            self, "导出成功",
            f"已导出加密备份：\n{target}\n\n"
            "备份与原文件同样加密，可用主密码在任何一台机器打开。")

    # ================= 锁定 / 闲置 =================
    def _touch(self):
        self._last_activity = time.time()

    def _check_idle(self):
        if not self.db:
            return
        m = self.db.settings.get("auto_lock_min", 5)
        if m > 0 and time.time() - self._last_activity > m * 60:
            self.lock("已闲置自动锁定（可在设置中调整）")

    def lock(self, msg: str = ""):
        # 有未保存修改时先自动保存（防丢失优先）
        if self.editor.is_dirty() and self.view.get("sel"):
            try:
                ne = self.editor.collect()
                if ne.title:
                    self.on_save_form(ne)
            except Exception:        # noqa: BLE001
                pass
        self.persist()
        self.vault.wipe()                       # 密钥清零
        self.vault = None
        self.db = None
        self.undo_mgr.clear()                   # 撤销栈含明文副本，一并清除
        self.clip.cancel_all()
        self.view = {"cat": "all", "search": "", "sel": None}
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.cat_list.clear()
        self.entry_list.clear()
        self.editor._load_empty()
        self.locked.emit()
        if msg:
            toast(self, msg)

    # ================= 应用级事件（图片粘贴捕获） =================
    def _handle_paste(self) -> bool:
        """剪贴板是纯图片且正在编辑条目时，捕获为条目图片。返回是否拦截。"""
        cb = QGuiApplication.clipboard()
        if not (cb.hasImage() and not cb.hasText()):
            return False
        if not self.view.get("sel") or self.editor.is_empty():
            return False
        img = cb.image()
        if img.isNull():
            return False
        self.editor.add_image_qimage(img)
        toast(self, "已捕获粘贴的图片")
        return True

    # ================= 关闭 =================
    def closeEvent(self, ev):
        if self.editor.is_dirty():
            r = QMessageBox.question(
                self, "未保存的修改", "当前条目有未保存的修改，退出前保存吗？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if r == QMessageBox.Cancel:
                ev.ignore()
                return
            if r == QMessageBox.Yes:
                try:
                    ne = self.editor.collect()
                    if ne.title:
                        self.on_save_form(ne)
                except Exception:    # noqa: BLE001
                    pass
        self.persist()
        if self.vault:
            self.vault.wipe()
        super().closeEvent(ev)
