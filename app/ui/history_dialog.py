"""历史版本对话框：列表（滚动）+ 预览 + 恢复。

版本号规则与 demo 一致：索引 0 是最新快照，最初保存的内容为第 1 版，
即索引 i 的版本号 = 总数 - i；列表展示最新在上、最早在下。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.core.models import Entry


def _fmt(iso: str) -> str:
    return iso.replace("T", " ")[:16] if iso else ""


class HistoryDialog(QDialog):
    restore_requested = Signal(int)      # 被恢复版本在 history 中的索引

    def __init__(self, entry: Entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(f"历史版本 — 「{entry.title or '未命名'}」")
        self.setModal(True)
        self.resize(640, 520)
        self._show_pw = False
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        total = len(self.entry.history)
        head = QLabel(f"每次保存前旧内容自动快照，当前共 {total} 版"
                      f"（可在设置中调整保留数）。恢复前会先自动快照当前内容，"
                      f"恢复操作本身也可再撤销。")
        head.setWordWrap(True)
        head.setStyleSheet("color:#64748b;font-size:11.5px;border:none;")
        lay.addWidget(head)

        self.list_w = QListWidget()
        self.list_w.setObjectName("histList")
        for i, h in enumerate(self.entry.history):
            tag = "最新" if i == 0 else f"第 {total - i} 版"
            item = QListWidgetItem(f"🕘 {_fmt(h.saved_at)}　[{tag}]\n{h.reason}")
            item.setData(Qt.UserRole, i)
            self.list_w.addItem(item)
        if not total:
            self.list_w.addItem(QListWidgetItem("该条目还没有历史版本\n（每次保存时自动快照旧内容）"))
        self.list_w.itemClicked.connect(lambda it: self._preview(it.data(Qt.UserRole)))
        lay.addWidget(self.list_w, 2)

        # 预览区
        self.preview_host = QWidget()
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(self.preview_host)
        lay.addWidget(self.preview_scroll, 3)

        foot = QHBoxLayout()
        tip = QLabel("点击左侧版本查看内容")
        tip.setStyleSheet("color:#64748b;font-size:11.5px;border:none;")
        foot.addWidget(tip)
        foot.addStretch(1)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.reject)
        foot.addWidget(b_close)
        self.b_restore = QPushButton("↩ 恢复此版本")
        self.b_restore.setProperty("primary", True)
        self.b_restore.setEnabled(False)
        self.b_restore.clicked.connect(self._restore)
        foot.addWidget(self.b_restore)
        lay.addLayout(foot)

        if total:
            self.list_w.setCurrentRow(0)
            self._preview(0)

    def _preview(self, index: int):
        if index is None or index < 0 or index >= len(self.entry.history):
            return
        h = self.entry.history[index]
        snap = h.snap
        total = len(self.entry.history)
        tag = "最新" if index == 0 else f"第 {total - index} 版"

        form = QFormLayout(self.preview_host)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(7)
        form.labelAlignment = Qt.AlignRight

        def add_row(k, v):
            lbl = QLabel(str(v))
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setWordWrap(True)
            form.addRow(k, lbl)
            return lbl

        add_row("版本", f"第 {total - index} 版 · {_fmt(h.saved_at)}" + ("（最新）" if index == 0 else f"　[{tag}]"))
        add_row("标题", snap.get("title") or "（未命名）")
        add_row("分类", snap.get("category") or "—")
        fields = snap.get("fields", {})
        if self.entry.type == "password":
            add_row("账号", fields.get("username") or "—")
            self._pw_lbl = add_row("密码", self._pw_text(fields))
            btn_row = QWidget()
            hbl = QHBoxLayout(btn_row)
            hbl.setContentsMargins(0, 0, 0, 0)
            b_eye = QPushButton("👁 显示 / 隐藏密码")
            b_eye.setProperty("flat", True)
            b_eye.clicked.connect(self._toggle_pw)
            hbl.addWidget(b_eye)
            hbl.addStretch(1)
            form.addRow("", btn_row)
            add_row("网址", fields.get("url") or "—")
            add_row("备注", fields.get("notes") or "—")
        else:
            add_row("内容", fields.get("content") or "—")
        add_row("图片", f"{len(snap.get('images', []))} 张")

        self._current_index = index
        self.b_restore.setEnabled(True)

    def _pw_text(self, fields) -> str:
        pw = fields.get("password") or ""
        return pw if self._show_pw else "•" * min(len(pw) or 8, 16)

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        if getattr(self, "_pw_lbl", None) is not None:
            self._pw_lbl.setText(self._pw_text(self.entry.history[self._current_index].snap.get("fields", {})))

    def _restore(self):
        idx = getattr(self, "_current_index", -1)
        if idx >= 0:
            self.restore_requested.emit(idx)
            self.accept()
