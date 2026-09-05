"""密码强度评估（简化版 zxcvbn，与 demo 同源算法）。

按字符空间估算熵，再对常见弱密码、纯数字、重复字符、键盘序列做惩罚，
输出 0~4 级评分。
"""
from __future__ import annotations

import math

COMMON_PW = frozenset("""123456 password 123456789 12345678 1234567 1234567890
qwerty 123123 111111 1234567 abc123 123qwe qwerty123 1qaz2wsx password1
iloveyou admin admin123 root welcome monkey dragon letmein login princess
qwertyuiop solo freedom whatever qazwsx zaq12wsx 666666 888888 5201314
a123456 123321 aa12345680 woaini1314 woaini147258369 1q2w3e4r asdfghjkl
trustno1 sunshine master hello freedom whatever superman shadow baseball
soccer hockey killer george jessica hunter summer winter banana pepper""".split())

KB_SEQ = ["qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890", "abcdefghijklmnopqrstuvwxyz"]

LABELS = ["—", "弱", "一般", "强", "极强"]


def evaluate(password: str) -> dict:
    """返回 {score:0-4, label, bits, note}。"""
    if not password:
        return {"score": 0, "label": LABELS[0], "bits": 0, "note": ""}

    charset = 0
    if any(c.islower() for c in password):
        charset += 26
    if any(c.isupper() for c in password):
        charset += 26
    if any(c.isdigit() for c in password):
        charset += 10
    if any(not c.isalnum() for c in password):
        charset += 33

    bits = len(password) * math.log2(charset or 1)
    notes: list[str] = []
    lp = password.lower()

    if lp in COMMON_PW:
        bits = min(bits, 8)
        notes.append("常见弱密码")
    if password.isdigit():
        bits *= 0.65
        notes.append("纯数字")
    if len(set(password)) == 1:
        bits = min(bits, 10)
        notes.append("重复字符")
    for seq in KB_SEQ:
        hit = False
        for i in range(len(seq) - 3):
            if seq[i:i + 4] in lp:
                bits *= 0.85
                notes.append("键盘序列")
                hit = True
                break
        if hit:
            break

    bits = round(bits)
    score = 1 if bits < 40 else 2 if bits < 60 else 3 if bits < 80 else 4
    return {"score": score, "label": LABELS[score], "bits": bits, "note": "、".join(notes)}
