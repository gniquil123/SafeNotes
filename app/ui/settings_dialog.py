"""设置对话框：安全设置 + 修改主密码 + 导出加密备份。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.unlock_dialog import StrengthBar
from app.utils.strength import evaluate


class ChangePasswordDialog(QDialog):
    """修改主密码（三段输入 + 强度提示）。实际重加密由主窗口执行。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改主密码")
        self.setModal(True)
        self.setMinimumWidth(420)

        from PySide6.QtWidgets import QLineEdit
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(8)

        warn = QLabel("修改后立即用新密码重新加密整个保险库（修改前会自动备份）。")
        warn.setStyleSheet("color:#9a3412;background:#fff7ed;border:1px solid #fed7aa;"
                           "border-radius:8px;padding:8px;font-size:11.5px;")
        warn.setWordWrap(True)
        v.addWidget(warn)

        form = QFormLayout()
        self.old_edit = QLineEdit()
        self.old_edit.setEchoMode(QLineEdit.Password)
        form.addRow("当前主密码", self.old_edit)
        self.new_edit = QLineEdit()
        self.new_edit.setEchoMode(QLineEdit.Password)
        form.addRow("新主密码", self.new_edit)
        self.strength = StrengthBar()
        self.new_edit.textChanged.connect(self.strength.update_password)
        form.addRow("", self.strength)
        self.new2_edit = QLineEdit()
        self.new2_edit.setEchoMode(QLineEdit.Password)
        form.addRow("确认新密码", self.new2_edit)
        v.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("确认修改")
        btns.button(QDialogButtonBox.Ok).setProperty("primary", True)
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _validate(self):
        if not self.old_edit.text():
            QMessageBox.warning(self, "缺少输入", "请输入当前主密码。")
            return
        np = self.new_edit.text()
        if not np:
            QMessageBox.warning(self, "缺少输入", "请输入新主密码。")
            return
        if evaluate(np)["score"] < 2:
            r = QMessageBox.warning(
                self, "密码强度偏弱",
                "新主密码强度较弱，抗暴力破解能力不足，仍要使用吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        if np != self.new2_edit.text():
            QMessageBox.warning(self, "不一致", "两次输入的新密码不一致。")
            return
        self.accept()

    @property
    def old_password(self):
        return self.old_edit.text()

    @property
    def new_password(self):
        return self.new_edit.text()


class SettingsDialog(QDialog):
    apply_requested = Signal(dict)               # 四项设置
    change_password_requested = Signal(str, str)  # 旧密码, 新密码
    export_backup_requested = Signal()

    LOCK_OPTS = [(0, "不锁定"), (1, "1 分钟"), (3, "3 分钟"), (5, "5 分钟"), (10, "10 分钟")]
    CLIP_OPTS = [(0, "不清除"), (10, "10 秒"), (20, "20 秒"), (30, "30 秒"), (60, "60 秒")]
    HIST_OPTS = [(10, "10 版"), (20, "20 版"), (50, "50 版")]

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(460)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 14)
        v.setSpacing(10)

        form = QFormLayout()
        self.lock_cb = QComboBox()
        for val, txt in self.LOCK_OPTS:
            self.lock_cb.addItem(txt, val)
        self.lock_cb.setCurrentIndex(
            next((i for i, (val, _) in enumerate(self.LOCK_OPTS)
                  if val == settings.get("auto_lock_min", 5)), 3))
        form.addRow("闲置自动锁定", self.lock_cb)

        self.clip_cb = QComboBox()
        for val, txt in self.CLIP_OPTS:
            self.clip_cb.addItem(txt, val)
        self.clip_cb.setCurrentIndex(
            next((i for i, (val, _) in enumerate(self.CLIP_OPTS)
                  if val == settings.get("clip_sec", 20)), 2))
        form.addRow("剪贴板自动清除", self.clip_cb)

        self.hist_cb = QComboBox()
        for val, txt in self.HIST_OPTS:
            self.hist_cb.addItem(txt, val)
        self.hist_cb.setCurrentIndex(
            next((i for i, (val, _) in enumerate(self.HIST_OPTS)
                  if val == settings.get("history_keep", 20)), 1))
        form.addRow("历史版本保留数", self.hist_cb)

        self.theme_cb = QComboBox()
        self.theme_cb.addItem("浅色", "light")
        self.theme_cb.addItem("深色", "dark")
        self.theme_cb.setCurrentIndex(0 if settings.get("theme", "light") == "light" else 1)
        form.addRow("界面主题", self.theme_cb)
        v.addLayout(form)

        tip1 = QLabel("自动锁定：闲置指定时间后清除内存中的密钥与明文并回到解锁界面")
        tip2 = QLabel("剪贴板自动清除：复制密码后到时自动清空（若内容未被覆盖）")
        for t in (tip1, tip2):
            t.setStyleSheet("color:#64748b;font-size:11px;border:none;")
            t.setWordWrap(True)
            v.addWidget(t)

        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#e2e8f0;border:none;")
        v.addWidget(line)

        actions = QHBoxLayout()
        b_pw = QPushButton("🔑 修改主密码")
        b_pw.clicked.connect(self._change_pw)
        actions.addWidget(b_pw)
        b_export = QPushButton("📦 导出加密备份")
        b_export.clicked.connect(self.export_backup_requested.emit)
        actions.addWidget(b_export)
        actions.addStretch(1)
        v.addLayout(actions)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存设置")
        btns.button(QDialogButtonBox.Ok).setProperty("primary", True)
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _on_ok(self):
        self.apply_requested.emit({
            "auto_lock_min": self.lock_cb.currentData(),
            "clip_sec": self.clip_cb.currentData(),
            "history_keep": self.hist_cb.currentData(),
            "theme": self.theme_cb.currentData(),
        })
        self.accept()

    def _change_pw(self):
        dlg = ChangePasswordDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.change_password_requested.emit(dlg.old_password, dlg.new_password)
