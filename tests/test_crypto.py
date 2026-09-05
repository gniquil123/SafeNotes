"""加密核心测试：派生、往返、错误密码、篡改检测、原子写、备份轮换。"""
import json

import pytest

from app.crypto import vault
from app.crypto.vault import (
    VaultFormatError, WrongPasswordError,
    atomic_write, change_password, create_vault, open_vault, rotate_backups,
)


def make_db(n=2):
    return {
        "format": {"version": 1},
        "settings": {"auto_lock_min": 5, "clip_sec": 20, "history_keep": 20, "theme": "light"},
        "entries": [
            {"id": f"id-{i}", "type": "password", "title": f"条目{i}",
             "category": "工作", "fields": {"username": "u", "password": "p", "url": "", "notes": ""},
             "images": [], "deleted": False, "deleted_at": None, "history": [],
             "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}
            for i in range(n)
        ],
    }


def test_kdf_deterministic():
    from app.crypto.kdf import derive_key
    k1 = derive_key("密码123", b"s" * 32, 1, 8 * 1024, 1)
    k2 = derive_key("密码123", b"s" * 32, 1, 8 * 1024, 1)
    k3 = derive_key("密码124", b"s" * 32, 1, 8 * 1024, 1)
    k4 = derive_key("密码123", b"t" * 32, 1, 8 * 1024, 1)
    assert k1 == k2 and len(k1) == 32
    assert k1 != k3 and k1 != k4


def test_create_open_roundtrip(tmp_path):
    p = tmp_path / "test.vault"
    db = make_db()
    v, db2 = create_vault(p, "主密码", db)
    try:
        assert p.exists()
        # 明文不得出现在磁盘文件中
        raw = p.read_bytes()
        assert "条目0".encode() not in raw
        assert b"password" not in raw.lower() or b"fields" not in raw

        v2, db3 = open_vault(p, "主密码")
        try:
            assert db3["entries"][0]["title"] == "条目0"
            assert db3 == db2
        finally:
            v2.wipe()
    finally:
        v.wipe()


def test_wrong_password(tmp_path):
    p = tmp_path / "t.vault"
    v, _ = create_vault(p, "正确密码", make_db())
    v.wipe()
    with pytest.raises(WrongPasswordError):
        open_vault(p, "错误密码")


def test_save_and_reopen(tmp_path):
    p = tmp_path / "t.vault"
    v, db = create_vault(p, "pw", make_db(1))
    try:
        db["entries"].append({"id": "x9", "type": "note", "title": "新笔记",
                              "category": "默认", "fields": {"content": "内容"},
                              "images": [], "deleted": False, "deleted_at": None,
                              "history": [], "created_at": "t", "updated_at": "t"})
        v.save(db)
        v2, db2 = open_vault(p, "pw")
        try:
            assert len(db2["entries"]) == 2
            assert db2["entries"][-1]["title"] == "新笔记"
        finally:
            v2.wipe()
    finally:
        v.wipe()


def _flip_byte(p, offset):
    data = bytearray(p.read_bytes())
    data[offset] ^= 0x01
    p.write_bytes(bytes(data))


def test_payload_bitflip_detected(tmp_path):
    """单比特篡改必须被 GCM 检出。"""
    p = tmp_path / "t.vault"
    v, _ = create_vault(p, "pw", make_db())
    v.wipe()
    size = p.stat().st_size
    _flip_byte(p, size - 5)          # 篡改 payload 尾部
    with pytest.raises((VaultFormatError, WrongPasswordError)):
        open_vault(p, "pw")


def test_verifier_bitflip_detected(tmp_path):
    p = tmp_path / "t.vault"
    v, _ = create_vault(p, "pw", make_db())
    v.wipe()
    _flip_byte(p, 22 + 32 + 30)      # 篡改 verifier 密文
    with pytest.raises(WrongPasswordError):
        open_vault(p, "pw")


def test_header_tamper_detected(tmp_path):
    """头部（KDF 参数 / salt）是 AAD，篡改导致认证失败。"""
    p = tmp_path / "t.vault"
    v, _ = create_vault(p, "pw", make_db())
    v.wipe()
    _flip_byte(p, 12)                # memory_cost 字节
    with pytest.raises(WrongPasswordError):
        open_vault(p, "pw")


def test_nonce_unique_each_save(tmp_path):
    p = tmp_path / "t.vault"
    v, db = create_vault(p, "pw", make_db())
    try:
        first = p.read_bytes()
        v.save(db)
        second = p.read_bytes()
        assert first != second                      # nonce 随机，密文必然不同
        # verifier 位置固定，payload nonce 位置在 verifier 之后
        off = 22 + 32 + 60
        assert first[off:off + 12] != second[off:off + 12]
    finally:
        v.wipe()


def test_atomic_write_no_tmp_left(tmp_path):
    p = tmp_path / "t.vault"
    atomic_write(p, b"abc")
    atomic_write(p, b"abcdef")
    assert p.read_bytes() == b"abcdef"
    assert not list(tmp_path.glob("*.tmp"))


def test_rotate_backups(tmp_path):
    p = tmp_path / "t.vault"
    p.write_bytes(b"v1")
    rotate_backups(p); p.write_bytes(b"v2")
    rotate_backups(p); p.write_bytes(b"v3")
    rotate_backups(p); p.write_bytes(b"v4")
    baks = sorted(tmp_path.glob("*.bak.*"))
    assert len(baks) == 3
    assert p.with_name("t.vault.bak.1").read_bytes() == b"v3"
    assert p.with_name("t.vault.bak.2").read_bytes() == b"v2"
    assert p.with_name("t.vault.bak.3").read_bytes() == b"v1"

    # 超过 5 份时最旧的被丢弃
    for i in range(4, 9):
        rotate_backups(p); p.write_bytes(f"v{i}".encode())
    assert len(list(tmp_path.glob("*.bak.*"))) == 5


def test_change_password(tmp_path):
    p = tmp_path / "t.vault"
    v, db = create_vault(p, "旧密码", make_db())
    v.wipe()
    v2 = change_password(p, "旧密码", "新密码", db)
    try:
        with pytest.raises(WrongPasswordError):
            open_vault(p, "旧密码")
        v3, db3 = open_vault(p, "新密码")
        try:
            assert db3["entries"] == db["entries"]
        finally:
            v3.wipe()
        assert p.with_name("t.vault.bak.1").exists()   # 改密前自动备份
    finally:
        v2.wipe()


def test_magic_guard(tmp_path):
    p = tmp_path / "fake.vault"
    p.write_bytes(b"NOTVAULT" + b"\x00" * 200)
    with pytest.raises(VaultFormatError):
        open_vault(p, "pw")
