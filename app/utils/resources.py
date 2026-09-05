"""打包后资源路径解析。

开发态返回项目根目录；PyInstaller onefile 下 _MEIPASS 为临时解包目录
（build.bat 以 --add-data "assets;assets" 把 assets 打进包内）。
"""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(rel: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / rel
