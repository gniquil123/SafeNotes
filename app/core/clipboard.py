"""剪贴板安全复制：复制密码后倒计时自动清除。

清除前先比较剪贴板当前内容是否仍是当初复制的密码，
只有未被用户覆盖时才清空（桌面端可比浏览器可靠地做到这一点）。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


class ClipboardManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timers: list[QTimer] = []

    def copy_secret(self, text: str, clear_after_sec: int, on_cleared=None, on_skip=None) -> None:
        """复制文本；clear_after_sec > 0 时安排自动清除。回调用于 toast 提示。"""
        if not text:
            return
        QApplication.clipboard().setText(text)
        if clear_after_sec <= 0:
            return
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(lambda: self._clear(text, on_cleared, on_skip))
        t.start(clear_after_sec * 1000)
        self._timers.append(t)

    def _clear(self, expect: str, on_cleared, on_skip):
        cb = QApplication.clipboard()
        if cb.text() == expect:
            cb.clear()
            if on_cleared:
                on_cleared()
        else:
            if on_skip:
                on_skip()

    def cancel_all(self):
        for t in self._timers:
            t.stop()
        self._timers.clear()
