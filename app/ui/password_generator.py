"""密码生成器对话框：加密随机源（secrets）、长度 / 字符集可调。"""
from __future__ import annotations

import secrets
import string

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSlider, QVBoxLayout,
)

from app.ui.unlock_dialog import StrengthBar

CONFUSABLE = set("0O1lI|`'\"")

GEN_SETS = {
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "digit": string.digits,
    "symbol": "!@#$%^&*()-_=+[]{}<>?,.;:~",
}


def gen_password(length: int, lower=True, upper=True, digit=True,
                 symbol=True, no_confuse=True) -> str:
    sets = []
    if lower:
        sets.append(GEN_SETS["lower"])
    if upper:
        sets.append(GEN_SETS["upper"])
    if digit:
        sets.append(GEN_SETS["digit"])
    if symbol:
        sets.append(GEN_SETS["symbol"])
    if no_confuse:
        sets = ["".join(c for c in s if c not in CONFUSABLE) or s for s in sets]
    sets = [s for s in sets if s]
    if not sets:
        return ""
    pool = "".join(sets)
    chars = [secrets.choice(s) for s in sets]              # 每类至少一个
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    for i in range(len(chars) - 1, 0, -1):                 # Fisher-Yates
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars[:length])


class GeneratorDialog(QDialog):
    copy_secret = Signal(str, int)        # 文本, 清除秒数（由主窗口接管剪贴板）

    def __init__(self, target_edit=None, clip_sec: int = 20, parent=None):
        super().__init__(parent)
        self.target_edit = target_edit
        self.clip_sec = clip_sec
        self.setWindowTitle("密码生成器")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build_ui()
        self._regen()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        self.out_edit.setStyleSheet("font-family:Consolas,monospace;font-size:15px;"
                                    "letter-spacing:1px;text-align:center;padding:9px;")
        row.addWidget(self.out_edit)
        b_re = QPushButton("🔄")
        b_re.setToolTip("重新生成")
        b_re.setFixedWidth(42)
        b_re.clicked.connect(self._regen)
        row.addWidget(b_re)
        b_cp = QPushButton("📋")
        b_cp.setToolTip("复制（自动清除）")
        b_cp.setFixedWidth(42)
        b_cp.clicked.connect(lambda: self.copy_secret.emit(self.out_edit.text(), self.clip_sec))
        row.addWidget(b_cp)
        lay.addLayout(row)

        self.strength = StrengthBar()
        lay.addWidget(self.strength)

        len_row = QHBoxLayout()
        len_row.addWidget(QLabel("长度"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(8, 64)
        self.slider.setValue(20)
        self.val_lbl = QLabel("20")
        self.val_lbl.setStyleSheet(f"font-size:15px;font-weight:700;border:none;")
        self.val_lbl.setFixedWidth(36)
        self.val_lbl.setAlignment(Qt.AlignCenter)
        len_row.addWidget(self.slider)
        len_row.addWidget(self.val_lbl)
        lay.addLayout(len_row)

        chk_row = QHBoxLayout()
        self.cb_lower = QCheckBox("小写 a-z")
        self.cb_upper = QCheckBox("大写 A-Z")
        self.cb_digit = QCheckBox("数字 0-9")
        self.cb_symbol = QCheckBox("符号 !@#")
        self.cb_noconf = QCheckBox("排除易混淆 (0O1lI)")
        for cb, on in ((self.cb_lower, True), (self.cb_upper, True),
                       (self.cb_digit, True), (self.cb_symbol, True), (self.cb_noconf, True)):
            cb.setChecked(on)
            cb.stateChanged.connect(lambda *_: self._regen())
            chk_row.addWidget(cb)
        self.slider.valueChanged.connect(self._regen)
        lay.addLayout(chk_row)

        note = QLabel("使用 secrets 加密级随机源（CSPRNG）")
        note.setStyleSheet("color:#64748b;font-size:11px;border:none;")
        lay.addWidget(note)

        foot = QHBoxLayout()
        foot.addStretch(1)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.reject)
        foot.addWidget(b_close)
        self.b_use = QPushButton("✔ 使用此密码（填入表单）")
        self.b_use.setProperty("primary", True)
        self.b_use.clicked.connect(self._use)
        foot.addWidget(self.b_use)
        lay.addLayout(foot)

    def _regen(self):
        self.val_lbl.setText(str(self.slider.value()))
        pw = gen_password(self.slider.value(), self.cb_lower.isChecked(),
                          self.cb_upper.isChecked(), self.cb_digit.isChecked(),
                          self.cb_symbol.isChecked(), self.cb_noconf.isChecked())
        self.out_edit.setText(pw)
        self.strength.update_password(pw)

    def _use(self):
        if self.target_edit is not None:
            self.target_edit.setText(self.out_edit.text())
        self.accept()
