"""解锁 / 创建保险库对话框。

- 创建模式：主密码 + 确认 + 强度条 + 「密码丢失无法找回」警告
- 解锁模式：主密码 + 错误提示 + 连续错误退避倒计时（4~5 次 30 秒，≥6 次 5 分钟）
- Argon2id 派生在 QThread 中执行，避免 256MB 派生期间界面冻结
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from app.crypto import vault as vault_mod
from app.utils.strength import evaluate


class StrengthBar(QWidget):
    """四段式密码强度条 + 文本。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segs: list[QFrame] = []
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for _ in range(4):
            f = QFrame()
            f.setFixedHeight(5)
            f.setStyleSheet("background:#e2e8f0;border-radius:2px;")
            row.addWidget(f)
            self._segs.append(f)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addLayout(row)
        self.label = QLabel("强度：—")
        self.label.setStyleSheet(f"color:#64748b;font-size:11px;border:none;")
        lay.addWidget(self.label)

    def update_password(self, pw: str):
        r = evaluate(pw)
        colors = {1: "#dc2626", 2: "#f59e0b", 3: "#3b82f6", 4: "#16a34a"}
        for i, seg in enumerate(self._segs):
            on = i < r["score"]
            seg.setStyleSheet(
                f"background:{colors[r['score']] if on else '#e2e8f0'};border-radius:2px;")
        note = f"（{r['note']}）" if r["note"] else ""
        self.label.setText(
            f"强度：{r['label']}{note}" + (f"　≈ {r['bits']} bit 熵" if pw else ""))


class KdfWorker(QThread):
    """后台执行创建 / 解锁（Argon2id 派生 + AES-GCM 解密）。"""

    ok = Signal(object, object)          # SessionVault, db_dict
    failed = Signal(str, str)            # 错误类型: wrong|format|error, 消息

    def __init__(self, mode: str, path: Path, password: str, db_dict: dict | None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.path = path
        self.password = password
        self.db_dict = db_dict

    def run(self):
        try:
            if self.mode == "create":
                v, db = vault_mod.create_vault(self.path, self.password,
                                               self.db_dict or {"format": {"version": 1},
                                                                "settings": {}, "entries": []})
                self.ok.emit(v, db)
            else:
                v, db = vault_mod.open_vault(self.path, self.password)
                self.ok.emit(v, db)
        except vault_mod.WrongPasswordError:
            self.failed.emit("wrong", "主密码错误")
        except vault_mod.VaultFormatError as e:
            self.failed.emit("format", str(e))
        except Exception as e:                       # noqa: BLE001
            self.failed.emit("error", f"操作失败：{e}")


class UnlockDialog(QDialog):
    """mode: "create" | "unlock"。成功后 result_vault / result_db 可用。"""

    def __init__(self, mode: str, vault_path: Path, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.vault_path = Path(vault_path)
        self.result_vault = None
        self.result_db = None
        self.fail_count = 0
        self.lock_until = 0
        self._worker: KdfWorker | None = None

        self.setWindowTitle("加密记事本" if mode == "create" else "保险库已锁定")
        self.setModal(True)
        self.setFixedWidth(430)
        self._build_ui()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_lock_state)
        self._tick.start(500)

    # ---------- UI ----------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 26, 30, 22)
        lay.setSpacing(8)

        icon = QLabel("🔐")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:34px;border:none;background:transparent;")
        lay.addWidget(icon)

        title = QLabel("创建你的加密保险库" if self.mode == "create" else "保险库已锁定")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18px;font-weight:700;border:none;")
        lay.addWidget(title)

        sub = QLabel("设置一个主密码，它将是打开保险库的唯一钥匙" if self.mode == "create"
                     else "输入主密码解锁 · 密钥已从内存中清除")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#64748b;font-size:12px;border:none;")
        lay.addWidget(sub)

        path_lbl = QLabel(str(self.vault_path))
        path_lbl.setAlignment(Qt.AlignCenter)
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet("color:#94a3b8;font-size:10px;border:none;")
        lay.addWidget(path_lbl)

        def mk_label(t):
            l = QLabel(t)
            l.setStyleSheet("color:#475569;font-size:12px;font-weight:600;border:none;")
            return l

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet(
            "color:#dc2626;background:#fee2e2;border-radius:7px;padding:6px;"
            "font-size:12px;border:none;")
        self.err_lbl.setWordWrap(True)
        self.err_lbl.hide()

        if self.mode == "create":
            lay.addWidget(mk_label("主密码"))
            self.pw_edit = QLineEdit()
            self.pw_edit.setEchoMode(QLineEdit.Password)
            self.pw_edit.setPlaceholderText("请输入主密码")
            lay.addWidget(self.pw_edit)
            self.strength = StrengthBar()
            lay.addWidget(self.strength)
            self.pw_edit.textChanged.connect(self.strength.update_password)

            lay.addWidget(mk_label("确认主密码"))
            self.pw2_edit = QLineEdit()
            self.pw2_edit.setEchoMode(QLineEdit.Password)
            self.pw2_edit.setPlaceholderText("请再次输入主密码")
            lay.addWidget(self.pw2_edit)

            warn = QLabel("⚠️  主密码遗失将无法找回 —— 没有后门、没有重置途径，"
                          "任何人都无法（包括开发者）解密你的数据。请务必牢记。")
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color:#9a3412;background:#fff7ed;border:1px solid #fed7aa;"
                "border-radius:8px;padding:8px;font-size:11.5px;")
            lay.addWidget(warn)
            self.pw2_edit.returnPressed.connect(self._on_confirm)
        else:
            lay.addWidget(mk_label("主密码"))
            self.pw_edit = QLineEdit()
            self.pw_edit.setEchoMode(QLineEdit.Password)
            self.pw_edit.setPlaceholderText("输入主密码解锁")
            lay.addWidget(self.pw_edit)
            self.pw_edit.returnPressed.connect(self._on_confirm)
            self.pw2_edit = None
            self.strength = None

        self.count_lbl = QLabel("")
        self.count_lbl.setAlignment(Qt.AlignCenter)
        self.count_lbl.setStyleSheet(
            "color:#b45309;font-size:12.5px;font-weight:600;border:none;")
        self.count_lbl.hide()
        lay.addWidget(self.count_lbl)

        lay.addWidget(self.err_lbl)
        lay.addSpacing(6)

        self.btn = QPushButton("创建保险库" if self.mode == "create" else "解锁")
        self.btn.setProperty("primary", True)
        self.btn.setMinimumHeight(36)
        self.btn.clicked.connect(self._on_confirm)
        lay.addWidget(self.btn)

        foot = QLabel("🔒 数据加密存储于本机，关闭程序后需输入主密码解锁")
        foot.setAlignment(Qt.AlignCenter)
        foot.setWordWrap(True)
        foot.setStyleSheet("color:#94a3b8;font-size:10.5px;border:none;")
        lay.addWidget(foot)

        self.pw_edit.setFocus()

    # ---------- 交互 ----------
    def _penalty_ms(self) -> int:
        if self.fail_count >= 6:
            return 300000
        if self.fail_count >= 4:
            return 30000
        return 0

    def _refresh_lock_state(self):
        remain = self.lock_until - _now_ms()
        if remain > 0:
            self.btn.setEnabled(False)
            s = (remain + 999) // 1000
            self.count_lbl.setText(f"连续错误 {self.fail_count} 次，"
                                   f"请等待 {s // 60} 分 {s % 60} 秒后重试")
            self.count_lbl.show()
        elif not (self._worker and self._worker.isRunning()):
            self.btn.setEnabled(True)
            self.count_lbl.hide()

    def _show_error(self, msg: str):
        self.err_lbl.setText(msg)
        self.err_lbl.show()
        QTimer.singleShot(4000, self.err_lbl.hide)

    def _on_confirm(self):
        if self._worker and self._worker.isRunning():
            return
        if self.lock_until > _now_ms():
            return
        pw = self.pw_edit.text()
        if not pw:
            self._show_error("请输入主密码")
            return

        if self.mode == "create":
            from app.utils.strength import evaluate as ev
            if ev(pw)["score"] < 2:
                from PySide6.QtWidgets import QMessageBox
                r = QMessageBox.warning(
                    self, "密码强度偏弱",
                    "主密码强度较弱，抗暴力破解能力不足。\n\n"
                    "建议使用 12 位以上、混合大小写数字符号的密码。\n仍要使用该密码吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if r != QMessageBox.Yes:
                    return
            if pw != self.pw2_edit.text():
                self._show_error("两次输入的密码不一致")
                return

        self.btn.setEnabled(False)
        self.btn.setText("派生密钥中…（约 1 秒）")
        self.err_lbl.hide()

        self._worker = KdfWorker(self.mode, self.vault_path, pw, None)
        self._worker.ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_ok(self, v, db):
        self.result_vault, self.result_db = v, db
        self.accept()

    def _on_fail(self, kind: str, msg: str):
        self.btn.setEnabled(True)
        self.btn.setText("解锁" if self.mode == "unlock" else "创建保险库")
        if kind == "wrong":
            self.fail_count += 1
            pen = self._penalty_ms()
            if pen:
                self.lock_until = _now_ms() + pen
            extra = f"（已连续错误 {self.fail_count} 次）" if self.fail_count > 1 else ""
            self._show_error("主密码错误" + extra + ("，触发等待惩罚" if pen else ""))
            self.pw_edit.clear()
            self.pw_edit.setFocus()
        else:
            self._show_error(msg)


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)
