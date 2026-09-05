"""密码强度评估测试。"""
from app.utils.strength import evaluate


def test_empty():
    assert evaluate("")["score"] == 0


def test_common_weak():
    r = evaluate("123456")
    assert r["score"] == 1 and "常见弱密码" in r["note"]


def test_pure_digits():
    assert evaluate("0102030405")["score"] == 1


def test_keyboard_sequence():
    r = evaluate("Qwerty!2026abcdefg")
    assert "键盘序列" in r["note"]


def test_strong():
    r = evaluate("Xk9#mQ2$vLp7!RtW")
    assert r["score"] >= 3 and r["bits"] >= 60


def test_very_strong():
    r = evaluate("Fh8@Nz3&Yw6*Qs1%Zm5!Ke9#Pq3@Xz7&")
    assert r["score"] == 4
