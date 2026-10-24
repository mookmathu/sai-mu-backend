# -*- coding: utf-8 -*-
"""
thai_text.py — ช่วยให้ข้อความไทยแสดงผลในแอปสวยขึ้น

1) add_word_breaks: แอปบางเครื่องตัดบรรทัดกลางคำ (เช่น "เช็|กรายละเอียด") เพราะแยกคำไทยผิด
   ใส่ ZERO WIDTH SPACE (U+200B) ระหว่างคำที่ตัดด้วย pythainlp (newmm) ให้เครื่องตัดบรรทัดตรงรอยต่อคำ
   ถ้าไม่ได้ติดตั้ง pythainlp จะคืนข้อความเดิม ไม่พัง
2) fix_maiyamok: ไม้ยมก (ๆ) เว้นวรรคหน้าและหลังเสมอ เช่น "ดี ๆ"
"""
from __future__ import annotations

import re

try:  # pythainlp เป็นตัวเลือก — ไม่มีก็ข้ามได้
    from pythainlp.tokenize import word_tokenize as _word_tokenize
except Exception:  # noqa: BLE001
    _word_tokenize = None

ZWSP = "​"
_THAI_CHAR = re.compile(r"[฀-๿]")


def fix_maiyamok(text: str) -> str:
    out = re.sub(r"[ \t]*ๆ", " ๆ", text)
    out = re.sub(r"ๆ(?=[^\s!?.,…~)\"'”’ๆ])", "ๆ ", out)
    out = re.sub(r"(?<=ๆ)[ \t]+(?=ๆ)", " ", out)
    out = re.sub(r"^[ \t]+ๆ", "ๆ", out, flags=re.MULTILINE)
    return re.sub(r"[ \t]{2,}", " ", out)


def strip_word_breaks(text: str) -> str:
    return text.replace(ZWSP, "")


def add_word_breaks(text: str) -> str:
    if not text or _word_tokenize is None:
        return text
    text = strip_word_breaks(text)
    lines = []
    for line in text.split("\n"):
        try:
            tokens = _word_tokenize(line, engine="newmm", keep_whitespace=True)
        except Exception:  # noqa: BLE001
            lines.append(line)
            continue
        buf = ""
        for tok in tokens:
            if buf and tok and _THAI_CHAR.match(buf[-1]) and _THAI_CHAR.match(tok[0]):
                buf += ZWSP
            buf += tok
        lines.append(buf)
    return "\n".join(lines)


def polish(text: str) -> str:
    return add_word_breaks(fix_maiyamok(text))


# --- ตัวอักษรไทยซ้อนผิดหลัก (โมเดลภาษาบางตัวพิมพ์เพี้ยน เช่น "ตะ๋") -----------------------------
_BAD_TONE_AFTER_A = re.compile("([ะาำ])[่-๋]")      # วรรณยุกต์หลัง ะ า ำ
_DOUBLE_MARK = re.compile("([ัิ-ฺ็-๎])\\1+")         # เครื่องหมายซ้อนซ้ำตัวเดิม
_ORPHAN_MARK = re.compile("(?<![ก-ฮะ-ฺ็-๎])[ัิ-ฺ็-๎]")


def has_invalid_thai(text: str) -> bool:
    """พบลำดับสระ/วรรณยุกต์ที่เขียนไม่ได้ในภาษาไทย"""
    if _BAD_TONE_AFTER_A.search(text) or _DOUBLE_MARK.search(text):
        return True
    return _ORPHAN_MARK.search(text.replace("​", " ")) is not None


def clean_invalid_thai(text: str) -> str:
    """ตัดเครื่องหมายที่ซ้อนผิดหลักออก (ใช้เป็นตาข่ายสุดท้ายหลังลองใหม่แล้ว)"""
    text = _BAD_TONE_AFTER_A.sub(r"\1", text)
    text = _DOUBLE_MARK.sub(r"\1", text)
    return _ORPHAN_MARK.sub("", text)
