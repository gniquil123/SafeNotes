"""生成应用图标（assets/icon.png 256px + assets/icon.ico 多尺寸）。

用法：QT_QPA_PLATFORM=offscreen python tools/make_icon.py
以 QPainter 绘制：蓝紫渐变圆角底 + 白色挂锁。改样式后重跑即可。
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QImage,
)
from PySide6.QtWidgets import QApplication


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0

    # 圆角渐变底
    bg = QPainterPath()
    bg.addRoundedRect(8 * s, 8 * s, 240 * s, 240 * s, 56 * s, 56 * s)
    grad = QLinearGradient(8 * s, 8 * s, 248 * s, 248 * s)
    grad.setColorAt(0, QColor("#2563eb"))
    grad.setColorAt(1, QColor("#7c3aed"))
    p.fillPath(bg, QBrush(grad))

    # 锁梁（半圆 + 两条竖腿）
    pen = QPen(QColor("white"), 18 * s, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(78 * s, 58 * s, 100 * s, 100 * s, 0, 180 * 16)
    p.drawLine(83 * s, 106 * s, 83 * s, 128 * s)
    p.drawLine(173 * s, 106 * s, 173 * s, 128 * s)

    # 锁体
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(64 * s, 120 * s, 128 * s, 90 * s, 16 * s, 16 * s)

    # 锁孔
    p.setBrush(QColor("#2563eb"))
    p.drawEllipse(117 * s, 142 * s, 22 * s, 22 * s)
    p.drawRoundedRect(123 * s, 158 * s, 10 * s, 26 * s, 5 * s, 5 * s)

    p.end()
    return img


def write_multi_ico(images: list[QImage], path: Path) -> None:
    """手写多尺寸 ICO：ICONDIR + ICONDIRENTRY×n + 每尺寸一张 PNG。

    Qt 自带的 ICO 写入只支持单图，小尺寸会由系统缩放导致发虚；
    多尺寸嵌入后 16/32/48px 等均为原生绘制，资源管理器 / 任务栏清晰。
    """
    pngs: list[bytes] = []
    for img in images:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        pngs.append(bytes(buf.data()))

    header = struct.pack("<HHH", 0, 1, len(pngs))          # 保留0, 类型=1(图标), 数量
    entries = b""
    body = b""
    offset = 6 + 16 * len(pngs)
    for img, data in zip(images, pngs):
        entries += struct.pack("<BBBBHHII",
                               img.width() % 256, img.height() % 256,   # 256 记为 0
                               0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)
    path.write_bytes(header + entries + body)


def main():
    app = QApplication(sys.argv)          # QPainter 需要 QGui 实例
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    draw(256).save(str(out / "icon.png"), "PNG")
    write_multi_ico([draw(s) for s in (16, 24, 32, 48, 64, 128, 256)], out / "icon.ico")
    print(f"icon written: {out / 'icon.png'} , {out / 'icon.ico'}")


if __name__ == "__main__":
    main()
