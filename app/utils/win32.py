"""Windows 平台辅助：防截屏 / 防录屏。

SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE = 0x11)：
Windows 10 2004+ 上截屏工具（Win+Shift+S、PrintScreen、OBS 等）
捕获到的该窗口区域为黑色/被排除。失败时静默返回 False，不影响主流程。
"""
from __future__ import annotations

import sys

WDA_EXCLUDEFROMCAPTURE = 0x11


def enable_anti_capture(widget) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        hwnd = int(widget.winId())
        ok = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        return bool(ok)
    except Exception:
        return False
