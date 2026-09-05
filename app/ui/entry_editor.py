"""条目编辑器：密码条目 / 笔记条目的表单与图片管理。

三种载入状态：空态、编辑已有条目、新建草稿。
表单修改 → dirty；保存由主窗口执行（此处只发出信号）。
"""
from __future__ import annotations

import base64

from shiboken6 import isValid
from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QDialog, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from app.core.models import Entry, ImageItem
from app.ui.unlock_dialog import StrengthBar

THUMB = 96


class ImagePreviewDialog(QDialog):
    def __init__(self, image: ImageItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle(image.name or "图片预览")
        pix = _pixmap_from_image(image)
        lay = QVBoxLayout(self)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        if not pix.isNull():
            if pix.width() > 1000 or pix.height() > 760:
                pix = pix.scaled(1000, 760, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl.setPixmap(pix)
            self.resize(pix.size() + self.contentsMargins() * 2)
        else:
            lbl.setText("（无法解码该图片）")
        lay.addWidget(lbl)


def _pixmap_from_image(image: ImageItem) -> QPixmap:
    try:
        return QPixmap.fromData(QByteArray(base64.b64decode(image.data)))
    except Exception:                                  # noqa: BLE001
        return QPixmap()


class _Thumb(QFrame):
    """缩略图卡片：图片 + 文件名 + 查看 / 移除。"""

    def __init__(self, image: ImageItem, on_remove, parent=None):
        super().__init__(parent)
        self.setObjectName("thumbCard")
        self.setFixedSize(THUMB + 20, THUMB + 58)
        self.image = image
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 6)
        lay.setSpacing(4)
        pix = _pixmap_from_image(image)
        lbl = QLabel()
        lbl.setObjectName("thumbLabel")
        lbl.setFixedSize(THUMB, THUMB)
        lbl.setAlignment(Qt.AlignCenter)
        if pix.isNull():
            lbl.setText("🖼")
        else:
            lbl.setPixmap(pix.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lbl.mousePressEvent = lambda *_: ImagePreviewDialog(image, self).exec()
        lay.addWidget(lbl, 0, Qt.AlignHCenter)
        name = QLabel(image.name or "（未命名）")
        name.setObjectName("imgName")
        name.setAlignment(Qt.AlignCenter)
        name.setFixedWidth(THUMB)
        lay.addWidget(name, 0, Qt.AlignHCenter)
        btns = QHBoxLayout()
        btns.setSpacing(4)
        b_view = QPushButton("查看")
        b_view.setFixedHeight(22)
        b_view.clicked.connect(lambda: ImagePreviewDialog(image, self).exec())
        btns.addWidget(b_view)
        if on_remove is not None:
            b_rm = QPushButton("移除")
            b_rm.setFixedHeight(22)
            b_rm.clicked.connect(on_remove)
            btns.addWidget(b_rm)
        lay.addLayout(btns)


class EntryEditor(QWidget):
    save_requested = Signal(object)      # Entry（收集自表单）
    cancel_requested = Signal()
    delete_requested = Signal()
    duplicate_requested = Signal()
    share_requested = Signal()
    history_requested = Signal()
    copy_secret = Signal(str)            # 密码复制（主窗口走安全剪贴板）
    dirty_changed = Signal(bool)

    def __init__(self, clip_sec_getter, parent=None):
        super().__init__(parent)
        self._clip_sec_getter = clip_sec_getter      # () -> int 自动清除秒数
        self._base: Entry | None = None
        self._is_draft = False
        self._form_images: list[ImageItem] = []
        self._dirty = False
        self._build_shell()

    # ---------- 外壳 ----------
    def _build_shell(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll)
        self._load_empty()

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 三种载入 ----------
    def _load_empty(self):
        self._base = None
        self._is_draft = False
        self._set_dirty(False)
        host = QWidget()
        v = QVBoxLayout(host)
        v.addStretch(3)
        icon = QLabel("🔐")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:48px;border:none;color:#94a3b8;")
        v.addWidget(icon)
        t1 = QLabel("从左侧选择一个条目，或点击顶部按钮新建")
        t1.setAlignment(Qt.AlignCenter)
        t1.setStyleSheet("color:#64748b;border:none;")
        v.addWidget(t1)
        t2 = QLabel("Ctrl+Z 撤销保存　Ctrl+Y 重做　Ctrl+S 保存")
        t2.setAlignment(Qt.AlignCenter)
        t2.setStyleSheet("color:#94a3b8;font-size:11.5px;border:none;")
        v.addWidget(t2)
        v.addStretch(4)
        self.scroll.setWidget(host)

    def is_empty(self) -> bool:
        return self._base is None

    def load_entry(self, entry: Entry, categories: list[str]):
        self._base = entry
        self._is_draft = False
        self._form_images = [ImageItem(im.name, im.data) for im in entry.images]
        self._build_form(entry, False, categories)
        self._set_dirty(False)

    def load_draft(self, entry_type: str, categories: list[str], category: str = ""):
        e = Entry.new(entry_type)
        if category:
            e.category = category
        self._base = e
        self._is_draft = True
        self._form_images = []
        self._build_form(e, True, categories, preset_category=category)
        self._set_dirty(False)

    def load_duplicate(self, src: Entry, categories: list[str]):
        """以已有条目为模板新建草稿：保留分类 / 账号 / 密码 / 内容 / 图片，标题加「（副本）」。

        未保存前取消则不产生任何数据；保存走正常新建流程（可撤销）。
        """
        e = Entry.new(src.type)
        e.title = (src.title or "未命名") + "（副本）"
        e.category = src.category
        import copy as _copy
        e.fields = _copy.deepcopy(src.fields)
        self._base = e
        self._is_draft = True
        self._form_images = [ImageItem(im.name, im.data) for im in src.images]
        self._build_form(e, True, categories)
        self._set_dirty(False)

    # ---------- 表单 ----------
    def _build_form(self, entry: Entry, is_draft: bool, categories: list[str],
                    preset_category: str = ""):
        host = QWidget()
        card = QFrame()
        card.setProperty("card", True)
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        outer.addStretch(1)

        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(4)

        # 头部
        head = QHBoxLayout()
        tag = QLabel(("新建" if is_draft else "编辑") +
                     (" · 🔑 密码条目" if entry.type == "password" else " · 📝 笔记"))
        tag.setStyleSheet(
            f"background:#dbeafe;color:#2563eb;border-radius:10px;"
            f"padding:2px 9px;font-size:11px;font-weight:700;")
        head.addWidget(tag)
        self._dirty_lbl = QLabel("")
        self._dirty_lbl.setStyleSheet("color:#f59e0b;font-size:11px;border:none;")
        head.addWidget(self._dirty_lbl)
        head.addStretch(1)
        meta = QLabel("尚未保存（保存后加密入库）" if is_draft
                      else f"更新于 {entry.updated_at.replace('T', ' ')[:16]}")
        meta.setStyleSheet("color:#94a3b8;font-size:10.5px;border:none;")
        head.addWidget(meta)
        v.addLayout(head)
        v.addSpacing(6)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignRight)
        v.addLayout(form)

        def label(t):
            return QLabel(t)

        self.title_edit = QLineEdit(entry.title)
        self.title_edit.setPlaceholderText("例如：GitHub 账号" if entry.type == "password"
                                           else "例如：服务器巡检笔记")
        form.addRow(label("标题 *"), self.title_edit)

        # 分类：可下拉选择已有分类，也可输入新分类（带补全）
        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        cur_cat = preset_category or entry.category or "默认"
        cat_items = sorted({c for c in categories if c} | {cur_cat})
        self.category_edit.addItems(cat_items)
        self.category_edit.setCurrentText(cur_cat)
        cat_comp = QCompleter(cat_items)
        cat_comp.setFilterMode(Qt.MatchContains)
        self.category_edit.setCompleter(cat_comp)
        form.addRow(label("分类"), self.category_edit)

        if entry.type == "password":
            self.username_edit = QLineEdit(entry.fields.get("username", ""))
            self.username_edit.setPlaceholderText("手机号 / 邮箱 / 用户名")
            form.addRow(label("账号"), self.username_edit)

            pw_row = QHBoxLayout()
            self.password_edit = QLineEdit(entry.fields.get("password", ""))
            self.password_edit.setEchoMode(QLineEdit.Password)
            pw_row.addWidget(self.password_edit)
            self._b_eye = QToolButton()
            self._b_eye.setText("👁")
            self._b_eye.setToolTip("显示 / 隐藏密码")
            self._b_eye.clicked.connect(self._toggle_pw)
            pw_row.addWidget(self._b_eye)
            self._b_copy = QToolButton()
            self._b_copy.setText("📋")
            sec = self._clip_sec_getter()
            self._b_copy.setToolTip(f"复制密码（{sec} 秒后自动清除）" if sec else "复制密码")
            self._b_copy.clicked.connect(
                lambda: self.copy_secret.emit(self.password_edit.text()))
            pw_row.addWidget(self._b_copy)
            self._b_gen = QToolButton()
            self._b_gen.setText("🎲")
            self._b_gen.setToolTip("打开密码生成器")
            self._b_gen.clicked.connect(self.open_generator)
            pw_row.addWidget(self._b_gen)
            wrap = QWidget()
            wrap.setLayout(pw_row)
            form.addRow(label("密码"), wrap)

            self.pw_strength = StrengthBar()
            self.pw_strength.update_password(entry.fields.get("password", ""))
            self.password_edit.textChanged.connect(self.pw_strength.update_password)
            form.addRow("", self.pw_strength)

            self.url_edit = QLineEdit(entry.fields.get("url", ""))
            self.url_edit.setPlaceholderText("https://…")
            form.addRow(label("网址"), self.url_edit)

            self.notes_edit = QPlainTextEdit(entry.fields.get("notes", ""))
            self.notes_edit.setPlaceholderText("恢复码、绑定手机、备注…")
            self.notes_edit.setFixedHeight(84)
            form.addRow(label("备注"), self.notes_edit)
        else:
            self.content_edit = QPlainTextEdit(entry.fields.get("content", ""))
            self.content_edit.setPlaceholderText("在这里记录内容…（支持粘贴 / 拖入图片）")
            self.content_edit.setMinimumHeight(240)
            form.addRow(label("内容"), self.content_edit)

        # 图片区
        img_lbl = QLabel("图片")
        v.addWidget(label("图片（支持粘贴 / 拖入，点击查看大图）"))
        self.img_host = QWidget()
        self.img_grid = QGridLayout(self.img_host)
        self.img_grid.setContentsMargins(0, 0, 0, 0)
        self.img_grid.setSpacing(8)
        v.addWidget(self.img_host)
        self.setAcceptDrops(True)

        # 底部按钮
        v.addSpacing(10)
        foot = QHBoxLayout()
        b_save = QPushButton("💾 保存（Ctrl+S）")
        b_save.setProperty("primary", True)
        b_save.clicked.connect(self._on_save)
        foot.addWidget(b_save)
        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(self.cancel_requested.emit)
        foot.addWidget(b_cancel)
        if not is_draft:
            b_dup = QPushButton("⧉ 复制条目")
            b_dup.setToolTip("以此条目为模板新建：保留分类 / 账号 / 密码 / 内容 / 图片，改个账号名即可保存")
            b_dup.clicked.connect(self.duplicate_requested.emit)
            foot.addWidget(b_dup)
            b_share = QPushButton("📤 分享")
            b_share.setToolTip("把条目文本内容（含密码）复制到剪贴板，方便粘贴发送；到期自动清除")
            b_share.clicked.connect(self.share_requested.emit)
            foot.addWidget(b_share)
            b_del = QPushButton("🗑 删除")
            b_del.setProperty("danger", True)
            b_del.clicked.connect(self.delete_requested.emit)
            foot.addWidget(b_del)
        foot.addStretch(1)
        if not is_draft:
            self._b_hist = QPushButton(f"🕘 历史版本（{len(entry.history)}）")
            self._b_hist.clicked.connect(self.history_requested.emit)
            foot.addWidget(self._b_hist)
        v.addLayout(foot)

        # dirty 跟踪（文本输入 + 下拉选择都算修改）
        for w in self.findChildren(QLineEdit):
            w.textEdited.connect(lambda *_: self._set_dirty(True))
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(lambda *_: self._set_dirty(True))
        for w in self.findChildren(QPlainTextEdit):
            w.textChanged.connect(lambda *_: self._set_dirty(True))

        self.scroll.setWidget(host)
        self.title_edit.setFocus()

    # ---------- dirty ----------
    def _set_dirty(self, dirty: bool):
        if self._dirty != dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)
        lbl = getattr(self, "_dirty_lbl", None)
        if lbl is not None and isValid(lbl):
            lbl.setText("● 未保存" if dirty else "")

    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def is_draft(self) -> bool:
        return self._is_draft

    @property
    def base_entry(self) -> Entry | None:
        return self._base

    # ---------- 密码工具 ----------
    def _toggle_pw(self):
        self.password_edit.setEchoMode(
            QLineEdit.Normal if self.password_edit.echoMode() == QLineEdit.Password
            else QLineEdit.Password)

    def open_generator(self):
        from app.ui.password_generator import GeneratorDialog
        dlg = GeneratorDialog(target_edit=self.password_edit,
                              clip_sec=self._clip_sec_getter(), parent=self)
        dlg.copy_secret.connect(lambda t, s: self.copy_secret.emit(t))
        dlg.exec()

    # ---------- 图片 ----------
    def _refresh_images(self):
        self._clear_layout(self.img_grid)
        row = col = 0
        for i, im in enumerate(self._form_images):
            card = _Thumb(im, on_remove=lambda _, idx=i: self._remove_image(idx))
            self.img_grid.addWidget(card, row, col)
            col += 1
            if col > 4:
                col = 0
                row += 1
        add = QPushButton("＋\n添加图片")
        add.setFixedSize(THUMB + 20, THUMB + 58)
        add.setToolTip("支持任意大小图片")
        add.clicked.connect(self._pick_images)
        self.img_grid.addWidget(add, row, col)
        self._set_dirty(True)

    def _remove_image(self, idx: int):
        self._form_images.pop(idx)
        self._refresh_images()

    def _pick_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.ico);;所有文件 (*.*)")
        for f in files:
            self.add_image_file(f, mark_dirty=True)

    def add_image_file(self, path: str, mark_dirty: bool = False):
        try:
            raw = open(path, "rb").read()
        except OSError:
            return
        name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        self._form_images.append(ImageItem(name=name, data=base64.b64encode(raw).decode()))
        self._refresh_images()
        if not mark_dirty:
            self._set_dirty(True)

    def add_image_qimage(self, img: QImage):
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        raw = bytes(buf.data())
        buf.close()
        self._form_images.append(
            ImageItem(name=f"粘贴图片_{len(self._form_images) + 1}.png",
                      data=base64.b64encode(raw).decode()))
        self._refresh_images()

    # ---------- 拖放 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.add_image_file(url.toLocalFile(), mark_dirty=True)

    # ---------- 收集 ----------
    def _on_save(self):
        if not self.title_edit.text().strip():
            self.title_edit.setFocus()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "缺少标题", "请填写标题后再保存。")
            return
        self.save_requested.emit(self.collect())

    def collect(self) -> Entry:
        e = self._base.deep_copy()
        e.title = self.title_edit.text().strip()
        e.category = self.category_edit.currentText().strip() or "默认"
        if e.type == "password":
            e.fields["username"] = self.username_edit.text()
            e.fields["password"] = self.password_edit.text()
            e.fields["url"] = self.url_edit.text().strip()
            e.fields["notes"] = self.notes_edit.toPlainText()
        else:
            e.fields["content"] = self.content_edit.toPlainText()
        e.images = [ImageItem(im.name, im.data) for im in self._form_images]
        return e
