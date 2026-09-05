"""保险库文件格式与读写。

文件布局（全部为网络字节序）::

    MAGIC "SNVAULT" (8B)
    format version  (u16)
    time_cost       (u32)   ┐
    memory_cost     (u32)   ├ KDF 参数（明文，解锁时按此派生）
    parallelism     (u32)   ┘
    salt            (32B)
    verifier        (12B nonce + 32B 明文 + 16B GCM tag = 60B)
    payload         (12B nonce + JSON 密文 + 16B tag, 变长)

- verifier 是用主密钥加密的随机 32 字节：解密通过（GCM tag 校验）
  即证明主密码正确，不需要任何口令哈希。
- header（MAGIC 到 salt）整体作为 AAD 参与两处加解密：
  篡改任何头部字段都会导致认证失败，防止降级攻击。
- payload 是整个数据库的 JSON（条目、设置、历史版本、图片 base64）。
- 保存采用原子写（临时文件 + fsync + os.replace），断电不会得到半截文件。
"""
from __future__ import annotations

import json
import os
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .kdf import KDF_ALG, derive_key, active_params
from .secure import SecureKey

MAGIC = b"SNVAULT1"      # 8 字节魔数
FORMAT_VERSION = 1
NONCE_LEN = 12
SALT_LEN = 32
VERIFIER_PLAIN_LEN = 32
VERIFIER_BLOB_LEN = NONCE_LEN + VERIFIER_PLAIN_LEN + 16   # 60

_DB_FORMAT = {"version": 1}


class VaultError(Exception):
    """保险库相关错误基类。"""


class VaultFormatError(VaultError):
    """文件格式损坏或被篡改。"""


class WrongPasswordError(VaultError):
    """主密码错误（verifier 认证失败）。"""


@dataclass
class VaultMeta:
    time_cost: int
    memory_cost: int
    parallelism: int
    salt: bytes

    @property
    def header(self) -> bytes:
        return (MAGIC + struct.pack(">H", FORMAT_VERSION)
                + struct.pack(">III", self.time_cost, self.memory_cost, self.parallelism)
                + self.salt)


def _encrypt(aes: AESGCM, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    return nonce + aes.encrypt(nonce, plaintext, aad)


def _decrypt(aes: AESGCM, blob: bytes, aad: bytes) -> bytes:
    if len(blob) < NONCE_LEN + 16:
        raise VaultFormatError("密文块不完整")
    return aes.decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _dump_db(db_dict: dict) -> bytes:
    payload = dict(db_dict)
    payload.setdefault("format", _DB_FORMAT)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class SessionVault:
    """一次解锁会话：持有密钥、头部元数据与 verifier，负责加密保存。"""

    def __init__(self, path: Path, key: SecureKey, meta: VaultMeta, verifier: bytes):
        self.path = Path(path)
        self.key = key
        self.meta = meta
        self.verifier = verifier

    def save(self, db_dict: dict) -> None:
        aad = self.meta.header
        aes = AESGCM(self.key.raw)
        payload = _encrypt(aes, _dump_db(db_dict), aad)
        atomic_write(self.path, aad + self.verifier + payload)

    def wipe(self) -> None:
        self.key.wipe()


def create_vault(path: Path, password: str, db_dict: dict) -> tuple[SessionVault, dict]:
    """创建新保险库文件。返回 (会话, 数据库字典)。"""
    path = Path(path)
    t, m, p = active_params()
    meta = VaultMeta(t, m, p, os.urandom(SALT_LEN))
    key = SecureKey(derive_key(password, meta.salt, t, m, p))
    aad = meta.header
    aes = AESGCM(key.raw)
    verifier = _encrypt(aes, os.urandom(VERIFIER_PLAIN_LEN), aad)
    vault = SessionVault(path, key, meta, verifier)
    vault.save(db_dict)
    return vault, db_dict


def open_vault(path: Path, password: str) -> tuple[SessionVault, dict]:
    """打开并解锁保险库。密码错误抛 WrongPasswordError，损坏抛 VaultFormatError。"""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as e:
        raise VaultError(f"无法读取保险库文件：{e}") from e

    if len(data) < len(MAGIC) + 2 + 12 + SALT_LEN + VERIFIER_BLOB_LEN:
        raise VaultFormatError("文件太小，不是有效的保险库文件")
    if data[:8] != MAGIC:
        raise VaultFormatError("文件头标识不符，不是保险库文件")

    version, = struct.unpack(">H", data[8:10])
    if version != FORMAT_VERSION:
        raise VaultFormatError(f"不支持的文件版本 v{version}（本程序支持 v{FORMAT_VERSION}）")

    t, m, p = struct.unpack(">III", data[10:22])
    salt = data[22:22 + SALT_LEN]
    off = 22 + SALT_LEN
    verifier = data[off:off + VERIFIER_BLOB_LEN]
    payload = data[off + VERIFIER_BLOB_LEN:]
    if len(payload) < NONCE_LEN + 16:
        raise VaultFormatError("数据段不完整，文件可能被截断")

    meta = VaultMeta(t, m, p, salt)
    key = SecureKey(derive_key(password, salt, t, m, p))
    aes = AESGCM(key.raw)
    aad = meta.header

    try:
        _decrypt(aes, verifier, aad)
    except InvalidTag:
        key.wipe()
        raise WrongPasswordError("主密码错误") from None

    try:
        plain = _decrypt(aes, payload, aad)
    except InvalidTag:
        key.wipe()
        raise VaultFormatError("数据段校验失败：文件已损坏或被篡改") from None

    try:
        db = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise VaultFormatError(f"数据段解析失败：{e}") from e

    return SessionVault(path, key, meta, verifier), db


def change_password(path: Path, old_password: str, new_password: str,
                    db_dict: dict) -> SessionVault:
    """修改主密码：先验证旧密码，重新生成盐与密钥，全量重加密。

    修改前自动落一份滚动备份。返回绑定新密钥的会话（调用方负责替换旧会话并清零旧密钥）。
    """
    path = Path(path)
    old_vault, db = open_vault(path, old_password)      # 验证旧密码
    rotate_backups(path)
    try:
        old_vault.wipe()
        t, m, p = active_params()
        meta = VaultMeta(t, m, p, os.urandom(SALT_LEN))
        key = SecureKey(derive_key(new_password, meta.salt, t, m, p))
        aad = meta.header
        aes = AESGCM(key.raw)
        verifier = _encrypt(aes, os.urandom(VERIFIER_PLAIN_LEN), aad)
        vault = SessionVault(path, key, meta, verifier)
        vault.save(db)
        return vault
    finally:
        old_vault.wipe()


def rotate_backups(path: Path, keep: int = 5) -> None:
    """滚动备份：path → .bak.1，逐级后移，超出 keep 份的丢弃。

    在每次会话的首次保存前调用，保证磁盘上始终留有上一份可用密文。
    """
    path = Path(path)
    if not path.exists():
        return
    for i in range(keep - 1, 0, -1):
        src = path.with_name(f"{path.name}.bak.{i}")
        dst = path.with_name(f"{path.name}.bak.{i + 1}")
        if src.exists():
            os.replace(src, dst)
    shutil.copy2(path, path.with_name(f"{path.name}.bak.1"))
