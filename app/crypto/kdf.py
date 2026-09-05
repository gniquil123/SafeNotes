"""Argon2id 主密钥派生。

参数 m=256MiB, t=3, p=4：RFC 9106 高安全方向的均衡配置。
每次派生需要约 256MB 内存与数百毫秒计算，使离线暴力破解的
单次尝试成本极高（GPU/ASIC 加速被内存硬化特性抵消）。

测试与冒烟场景可通过环境变量 SAFENOTES_LOW_KDF=1 切换为轻量参数，
正式使用始终走默认参数。
"""
import os

from argon2.low_level import hash_secret_raw, Type

KDF_ALG = "argon2id"
KEY_LEN = 32          # 256-bit 主密钥
SALT_LEN = 32

DEFAULT_TIME_COST = 3
DEFAULT_MEMORY_COST = 256 * 1024   # KiB = 256 MiB
DEFAULT_PARALLELISM = 4

_LOW_KDF = os.environ.get("SAFENOTES_LOW_KDF") == "1"


def active_params() -> tuple[int, int, int]:
    """返回当前进程使用的 (time_cost, memory_cost, parallelism)。"""
    if _LOW_KDF:
        return 1, 8 * 1024, 1      # 测试用：8MB / 1 轮，毫秒级
    return DEFAULT_TIME_COST, DEFAULT_MEMORY_COST, DEFAULT_PARALLELISM


def derive_key(password: str, salt: bytes,
               time_cost: int | None = None,
               memory_cost: int | None = None,
               parallelism: int | None = None) -> bytes:
    """由主密码与盐派生 32 字节主密钥。"""
    t, m, p = active_params()
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost if time_cost is not None else t,
        memory_cost=memory_cost if memory_cost is not None else m,
        parallelism=parallelism if parallelism is not None else p,
        hash_len=KEY_LEN,
        type=Type.ID,
    )
