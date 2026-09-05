"""启动选择器：解锁上次保险库 / 打开其他文件 / 新建保险库。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout,
)


def _documents_dir() -> Path:
    loc = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(loc) if loc else Path.home() / "Documents"


class LauncherDialog(QDialog):
    """启动时选择本次要打开的保险库。

    exec() 后检查 choice: (路径, "unlock"|"create")；None 表示用户取消。
    """

    def __init__(self, last_path: Path | None, parent=None):
        super().__init__(parent)
        self.last_path = Path(last_path) if last_path else None
        self.choice: tuple[Path, str] | None = None
        self.setWindowTitle("加密记事本")
        self.setModal(True)
        self.setFixedWidth(450)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(8)

        icon = QLabel("🔐")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:32px;border:none;")
        lay.addWidget(icon)

        title = QLabel("选择本次要打开的保险库")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:16px;font-weight:700;border:none;")
        lay.addWidget(title)
        lay.addSpacing(6)

        exists = bool(self.last_path and self.last_path.exists())
        if self.last_path:
            pl = QLabel(str(self.last_path))
            pl.setWordWrap(True)
            pl.setStyleSheet("color:#64748b;font-size:11px;border:none;")
            pl.setAlignment(Qt.AlignCenter)
            lay.addWidget(pl)

        self.b_last = QPushButton("🔓 解锁此保险库")
        self.b_last.setProperty("primary", True)
        self.b_last.setDefault(True)
        self.b_last.setMinimumHeight(34)
        self.b_last.setEnabled(exists)
        self.b_last.clicked.connect(self._unlock_last)
        lay.addWidget(self.b_last)
        if self.last_path and not exists:
            miss = QLabel("⚠ 上次的文件不存在（已移动或删除）")
            miss.setStyleSheet("color:#dc2626;font-size:11px;border:none;")
            miss.setAlignment(Qt.AlignCenter)
            lay.addWidget(miss)

        lay.addSpacing(6)
        b_open = QPushButton("📂 打开其他保险库文件…")
        b_open.setMinimumHeight(32)
        b_open.clicked.connect(self._open_other)
        lay.addWidget(b_open)

        b_new = QPushButton("➕ 创建新保险库…")
        b_new.setMinimumHeight(32)
        b_new.clicked.connect(self._create_new)
        lay.addWidget(b_new)

        lay.addSpacing(6)
        foot = QHBoxLayout()
        foot.addStretch(1)
        b_quit = QPushButton("退出")
        b_quit.clicked.connect(self.reject)
        foot.addWidget(b_quit)
        lay.addLayout(foot)

    # ---------- 三个选择 ----------
    def _unlock_last(self):
        if self.last_path and self.last_path.exists():
            self.choice = (self.last_path, "unlock")
            self.accept()

    def _open_other(self):
        start = str(self.last_path.parent) if self.last_path else str(_documents_dir())
        target, _ = QFileDialog.getOpenFileName(
            self, "打开保险库文件", start,
            "加密保险库 (*.vault);;备份 (*.vault.bak.*);;所有文件 (*.*)")
        if not target:
            return
        self.choice = (Path(target), "unlock")
        self.accept()

    def _create_new(self):
        default = str(_documents_dir() / "加密记事本.vault")
        while True:
            target, _ = QFileDialog.getSaveFileName(
                self, "创建保险库文件", default, "加密保险库 (*.vault)")
            if not target:
                return
            if Path(target).exists():
                r = QMessageBox.warning(
                    self, "覆盖确认",
                    "目标文件已存在，继续将以全新保险库覆盖它，\n原内容（含全部备份链）无法恢复。确定覆盖吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if r != QMessageBox.Yes:
                    continue
            self.choice = (Path(target), "create")
            self.accept()
            return
