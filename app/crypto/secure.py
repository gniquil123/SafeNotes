"""主密钥的内存持有与清零。

Python 的 bytes 不可变、无法擦除，因此密钥统一以 bytearray 持有，
锁定 / 退出时显式覆写清零（best-effort；解释型语言无法抵御内存取证，
这一点在 README 威胁模型中如实说明）。
"""
from __future__ import annotations


def wipe(buf: bytearray | None) -> None:
    """将 bytearray 内容全部覆写为 0。"""
    if buf is None:
        return
    buf[:] = b"\x00" * len(buf)


class SecureKey:
    """32 字节主密钥的持有者：raw 访问、wipe 清零、bool 判断有效。"""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("主密钥长度必须为 32 字节")
        self._k = bytearray(key)

    @property
    def raw(self) -> bytes:
        """供 AESGCM 等接口使用的副本。"""
        return bytes(self._k)

    @property
    def is_valid(self) -> bool:
        return any(self._k)

    def wipe(self) -> None:
        wipe(self._k)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.wipe()

    def __bool__(self):
        return self.is_valid
