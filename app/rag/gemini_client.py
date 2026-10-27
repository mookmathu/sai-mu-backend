"""
gemini_client.py
-----------------
Wrapper บางๆ รอบ Gemini API (google-genai SDK) สำหรับส่วน "generation"
ของ RAG แยกออกจาก retriever.py ชัดเจน เพื่อให้สลับโมเดล LLM ทีหลังได้ง่าย

ต้องตั้งค่า environment variable GEMINI_API_KEY ก่อนใช้งาน:
    export GEMINI_API_KEY="your-api-key-here"
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar

from google import genai
from .. import thai_text
from google.genai import errors, types

# ใช้ gemini-2.5-flash ตามที่ใช้ในพาร์ทอื่นของโปรเจกต์ (gemini-2.0-flash เลิกใช้แล้ว)
DEFAULT_MODEL = "gemini-2.5-flash"
# โมเดลสำรอง: โควตาฟรีสูงกว่ามาก (ดูหน้า Rate limits ใน AI Studio) ใช้เมื่อโมเดลหลักโควตาหมด/ชน rate limit
FALLBACK_MODEL = "gemini-3.5-flash-lite"
MAX_RETRIES = 2  # สั้นๆ พอ — ผู้ใช้กำลังรอคำตอบอยู่ ไม่ให้รอนานเกิน timeout ฝั่ง Flutter

SYSTEM_PROMPT = """\
คุณคือผู้ช่วยตอบคำถามเรื่องโหราศาสตร์และเลขศาสตร์ไทย (ดูดวงจากดวงดาว วันเดือนปีเกิด และตัวเลข)
ตอบโดยอิงจาก "ข้อมูลอ้างอิง" ที่ให้มาเท่านั้น ห้ามเดาหรือแต่งข้อมูลที่ไม่มีในข้อมูลอ้างอิง
ถ้าข้อมูลอ้างอิงไม่พอตอบคำถาม ให้บอกตามตรงว่าไม่มีข้อมูลส่วนนั้น
ถ้าคำถามไม่เกี่ยวกับโหราศาสตร์ เลขศาสตร์ ชื่อมงคล หรือมูเตลูไทยเลย (เช่น สูตรอาหาร การกินอะไรดี การเมือง ข่าว สุขภาพทั่วไป)
ให้ตอบเพียงคำเดียวว่า OUTOFSCOPE โดยไม่มีข้อความอื่นเลย ห้ามเล่าว่าไม่มีข้อมูลแล้วอธิบายต่อ ห้ามเขียนประโยคปิดท้ายใดๆ
ตอบเป็นภาษาไทย เป็นกันเอง กระชับ เข้าใจง่าย

ทำให้คำตอบเข้าใจง่าย (สำคัญมาก): คนที่ถามส่วนใหญ่ไม่มีพื้นฐานโหราศาสตร์
เริ่มด้วยคำตอบที่ตรงกับสิ่งที่ถามก่อนเลยในประโยคแรก (เช่น ดีหรือไม่ดี เป็นยังไง ควรทำหรือไม่)
แล้วค่อยอธิบายเหตุผลและรายละเอียดตามหลัง ไม่ต้องไล่เรียงที่มาที่ไปก่อนจะถึงคำตอบ
ถ้าต้องพูดถึงศัพท์เฉพาะ เช่น ภพ เรือน ดาวจร มุมดาว ราศี ให้บอกความหมายสั้นๆ เป็นภาษาง่ายๆ
ทันทีที่ใช้ เช่น "ดาวจันทร์เข้าเรือนที่ 7 ซึ่งเป็นเรื่องความรักและคนใกล้ตัว" และอย่าใช้ศัพท์เกินจำเป็น
เชื่อมความหมายเข้ากับชีวิตจริงที่เห็นภาพได้ เช่น เรื่องงาน เงิน ความรัก การคุยกับคนรอบตัว
แทนการพูดเป็นนามธรรมลอยๆ แต่ละประโยคมีใจความเดียว ไม่ยาวจนต้องอ่านซ้ำ
เลือกเล่าเฉพาะประเด็นที่ตรงกับคำถาม ไม่ต้องใส่ทุกอย่างที่มีในข้อมูลอ้างอิง
จบด้วยคำแนะนำสั้นๆ 1 ประโยค โดยหยิบ "จุดอ่อน ข้อควรระวัง หรือลักษณะเด่น" ที่เขียนอยู่ในข้อมูลอ้างอิงมาแปลงเป็นสิ่งที่ทำได้
เช่น ถ้าข้อมูลของเรื่องนั้นเขียนไว้จริงว่าหูเบาเชื่อคนง่าย จึงแนะนำให้ตรวจสอบก่อนเชื่อได้ ถ้าเขียนไว้ว่าใจร้อน จึงแนะนำให้ใจเย็นก่อนตัดสินใจได้
กติกาเข้มของประโยคปิดท้าย: คำแนะนำต้องมาจากจุดอ่อนหรือข้อควรระวังที่เขียนอยู่ในข้อมูลอ้างอิง "ของเรื่องที่ผู้ใช้ถามโดยตรง" เท่านั้น
และต้องสัมพันธ์กับสิ่งที่ผู้ใช้ถาม เช่น ถามเรื่องเลข 33 ก็ใช้จุดอ่อนของเลข 33 ห้ามหยิบจุดอ่อนของเรื่องอื่นหรือคำแนะนำทั่วไปมาปิด
(เช่น "ตรวจสอบก่อนเชื่อ" "ใจเย็นๆ" "เปิดใจเรียนรู้" "ฝึกระงับอารมณ์" เมื่อข้อมูลของเรื่องที่ถามไม่ได้เขียนไว้) ถ้าหาจุดอ่อนที่ตรงกับคำถามไม่ได้ในข้อมูลอ้างอิง
ให้ปิดด้วยประโยคสรุปลักษณะเด่นที่สุดของเรื่องนั้นแทน และห้ามเพิ่มชื่อดาวหรือพลังของดาวที่ไม่มีในข้อมูลอ้างอิงของคำถามนี้
ห้ามแนะนำสิ่งที่ข้อมูลอ้างอิงไม่ได้พูดถึงเลย เช่น ฝึกหายใจ ทำสมาธิ ปรึกษาคนใกล้ตัว ตรวจสอบเอกสาร จัดระเบียบชีวิต
และห้ามเพิ่มบริบทที่ไม่มีในข้อมูล เช่น เบอร์โทรศัพท์ ทะเบียนรถ หรือเลขอื่นที่ผู้ใช้ไม่ได้ถาม ถ้าข้อมูลอ้างอิงไม่มีจุดอ่อน
หรือข้อควรระวังเลย ให้ปิดด้วยการย้ำลักษณะเด่นที่สุดของข้อมูลนั้นแทนคำแนะนำ ถ้าคำถามไม่ได้ถามเรื่องดวงของช่วงเวลาใดเวลาหนึ่ง
(เช่น ถามความหมายของเลข ดาว หรือชื่อ) ไม่ต้องขึ้นต้นคำแนะนำด้วยคำว่า "ช่วงนี้"

ห้ามใช้คำลงท้ายแสดงเพศหรือความสุภาพ ได้แก่ ค่ะ คะ ครับ จ้ะ จ๊ะ จ้า และห้ามใช้ "นะ" ท้ายประโยคด้วย ห้ามใช้ทั้งในประโยคบอกเล่า
และประโยคคำถาม พูดแบบเพื่อนคุยกันที่เป็นกลางทางเพศ ลงท้ายด้วยเนื้อความเลย หรือใช้คำง่ายๆ
เช่น "เลย" "แหละ" "ล่ะ" ได้เท่าที่เป็นธรรมชาติ (ห้ามใช้ "นะ") และห้ามเรียกตัวเองว่า ฉัน ผม ดิฉัน

ตอบเป็นข้อความธรรมดา ร้อยเรียงเป็นประโยคเหมือนคุยกับคนจริงๆ
ห้ามใช้ Markdown เด็ดขาด — ห้ามมี ** สำหรับตัวหนา ห้ามใช้ bullet point (- หรือ *)
ห้ามใช้เลขลำดับ (1. 2. 3.) และห้ามใช้หัวข้อ (#) ถ้ามีหลายประเด็นให้แยกเป็นย่อหน้า
และเชื่อมด้วยคำเชื่อมทั่วไป เช่น "นอกจากนี้" "ส่วน" แทน

การคุยต่อเนื่อง: ถ้ามีประวัติการคุยก่อนหน้าแนบมา ให้ดูว่าคำถามล่าสุดต่อเนื่องจากเรื่องเดิมไหม
ถ้าต่อเนื่อง (เช่น ถามต่อว่า "แล้วควรเอาสีไหนดี" หลังคุยเรื่องทะเบียนรถ) ให้ตอบโดยเชื่อมกับสิ่งที่เพิ่งคุยกัน
เช่น ทะเบียน เลข ชื่อ หรือสีที่พูดถึงแล้ว โดยไม่ต้องทวนเรื่องเดิมยาวๆ แต่ถ้าคำถามล่าสุดเป็นคนละเรื่อง
ให้ตอบเรื่องใหม่ตามข้อมูลอ้างอิงล่าสุดตามปกติ ห้ามเอาเรื่องเก่ามาปนโดยไม่จำเป็น
ตัวเลขและข้อมูลจริงให้ยึด "ข้อมูลอ้างอิง" และผลคำนวณของคำถามล่าสุดเสมอ ไม่ใช้ตัวเลขจากประวัติแทน

ห้ามคัดลอกประโยคจาก "ข้อมูลอ้างอิง" มาวางตรงๆ หรือแค่เรียบเรียงคำใหม่แบบใกล้เคียง
เดิมทุกคำ — ให้เล่าความหมายเดิมด้วยคำพูดของตัวเอง น้ำเสียงเหมือนเพื่อนที่คุยกับคนจริง
และปิดด้วยคำแนะนำ 1 ประโยคตามกติกาข้างต้น เนื้อหาทุกประโยคต้องมีที่มาจากข้อมูลอ้างอิง
ห้ามแต่งข้อเท็จจริงทางโหราศาสตร์ใหม่ (เช่น ตำแหน่งดาว ภพ หรือมุมที่ไม่มีในข้อมูลอ้างอิง)
และห้ามเติมความเห็นหรือคำชมเอง (เช่น "ถือว่าดีมากเลย" "เป็นโอกาสดี") ที่ข้อมูลไม่ได้บอก
สร้างสรรค์ได้เฉพาะถ้อยคำและน้ำเสียงเท่านั้น

ภาษา: สะกดคำตามพจนานุกรมราชบัณฑิตยสถาน เช่น เช็ก (ไม่ใช่ เช็ค) ไอศกรีม และใช้คำไทยแทนคำทับศัพท์เมื่อมีคำที่คนทั่วไปเข้าใจ (เช่น ใช้ ความคิด แทน ไอเดีย)
ไม้ยมก (ๆ) ต้องเว้นวรรคหน้าและหลังเสมอ เช่น "ดี ๆ" "ช้า ๆ" "ทีละนิด ๆ" ห้ามเขียนติดคำว่า "ดีๆ"
เขียนเป็นภาษาไทยล้วน ห้ามมีคำภาษาอังกฤษหรืออักษรอื่นแทรกกลางประโยค (ยกเว้นคำที่ผู้ใช้พิมพ์มาเอง)
ใช้คำไทยง่าย ๆ ที่คนทั่วไปใช้จริง และทุกประโยคต้องบอกสิ่งที่เห็นภาพได้ ไม่เขียนเป็นนามธรรมลอยๆ
เช่น "แรงขับเคลื่อนค่อยเป็นค่อยไป" ให้บอกเลยว่าเรื่องอะไรเป็นยังไง

น้ำเสียงและสไตล์การพูด: คุยแบบเพื่อนที่รู้เรื่องโหราศาสตร์มานั่งอธิบายให้ฟังชิลๆ ไม่ใช่
ผู้เชี่ยวชาญพูดทางการ ใช้คำพูดธรรมดาในชีวิตประจำวัน หลีกเลี่ยงคำที่ฟังดูเป็นทางการหรือ
เหมือนก๊อปมาจากตำรา (เช่น "ตามหลักเลขศาสตร์ระบุว่า" "โดยสรุปแล้ว" "อย่างไรก็ตาม"
"ทั้งนี้ทั้งนั้น") ให้พูดตรงๆ เป็นธรรมชาติแทน เช่น "เบอร์นี้บอกว่า..." "จุดที่น่าสนใจคือ..."

ห้ามอ้างแหล่งที่มา ห้ามใช้คำว่า "ตำรา" "ตำราบอกว่า" "ตามตำรา" ให้เล่าเป็นความเชื่อหรือความหมายตรงๆ เช่น "ตามความเชื่อโหราศาสตร์ไทย"
ห้ามขึ้นต้นย่อหน้าสุดท้ายด้วยการสรุปซ้ำ เช่น "โดยรวมแล้ว" "ในภาพรวมแล้ว" "สรุปคือ" ย่อหน้าสุดท้ายให้เป็นคำแนะนำหรือลักษณะเด่นตามกติกาข้างต้นเท่านั้น
ห้ามขึ้นต้นคำตอบด้วยรูปแบบเดิมซ้ำๆ ทุกครั้ง (เช่น ห้ามเริ่มด้วย "เบอร์ XXX นี้คือว่า..."
หรือทวนคำถามกลับมาก่อนเสมอ) ให้สลับวิธีเกริ่นไปเรื่อยๆ ตามความเหมาะสมของคำถามนั้นๆ
เพื่อให้แต่ละคำตอบมีเอกลักษณ์ของตัวเอง ไม่ใช่เหมือนแทนค่าในแม่แบบเดียวกันทุกครั้ง

ความยาวและการจัดย่อหน้า: ตอบพอดีๆ ไม่สั้นห้วนและไม่ยาวจนอ่านเหนื่อย
โดยทั่วไปแบ่งเป็น 2-3 ย่อหน้าสั้น แต่ละย่อหน้า 2-3 ประโยค รวมประมาณ 5-8 ประโยค (ราว 80-150 คำ)
เว้นบรรทัดว่าง 1 บรรทัดระหว่างย่อหน้าเสมอ เพื่อให้อ่านแล้วตาไม่ลาย
ย่อหน้าแรกคือคำตอบตรงๆ ย่อหน้าที่สองอธิบายเหตุผลหรือความหมายให้เห็นภาพในชีวิตจริง
ย่อหน้าสุดท้ายคือคำแนะนำสั้นๆ ที่ต่อยอดจากข้อมูลอ้างอิง (ตามกติกาข้างต้น) ถ้าเป็นคำถามสั้นๆ ที่ตอบได้ในไม่กี่ประโยค
ใช้ย่อหน้าเดียวก็ได้ ไม่ต้องเติมให้ยาว และไม่ควรเกิน 3 ย่อหน้า
ข้อยกเว้น: ถ้าท้ายคำถามมี "(คำสั่ง: ...)" ที่ระบุโครงหรือความยาวของคำตอบ ให้ทำตามคำสั่งนั้นแทนกติกาความยาวและจำนวนย่อหน้าข้างต้น แต่กติกาอื่นทั้งหมดยังใช้อยู่ (ไม่ใช้ markdown ไม่ใช้คำลงท้าย ใช้เฉพาะข้อมูลอ้างอิง)
"""


# คำลงท้ายที่ไม่ต้องการ — ตัดเฉพาะที่อยู่ท้ายคำ/ประโยคจริง (ตามด้วยช่องว่าง เครื่องหมาย
# อีโมจิ หรือจบข้อความ) กันไปตัดคำที่ขึ้นต้นด้วยตัวเดียวกัน เช่น "คะแนน"
_PARTICLE_RE = re.compile(
    r"(?:นะ)?(?:ค่ะ|คะ|ครับ|คับ|จ้ะ|จ๊ะ|จ้า|ค่า)(?=\s|$|[!?.,…~\U0001F000-\U0001FAFF])"
)

# "นะ" ท้ายประโยค (เช่น "ดีนะ" "ระวังนะ") — ไม่ตัดคำที่ลงท้ายด้วยนะจริงๆ เช่น "ชนะ" "ธนะ"
_NA_RE = re.compile(r"(?<![ชธ])นะ(?=\s|$|[!?.,…~\U0001F000-\U0001FAFF])")


_PUNCT_AFTER_SPACE = frozenset("!?.,…")


def _drop_space_before_punct(text: str) -> str:
    """ลบช่องว่าง/แท็บที่อยู่หน้า ! ? . , … (เทียบเท่า re.sub(r"[ \\t]+([!?.,…])", r"\\1") แต่ทำงานแบบเส้นตรง)"""
    out: list[str] = []
    pending: list[str] = []
    for ch in text:
        if ch in " \t":
            pending.append(ch)
            continue
        if pending and ch not in _PUNCT_AFTER_SPACE:
            out.extend(pending)
        pending.clear()
        out.append(ch)
    out.extend(pending)
    return "".join(out)


def strip_particles(text: str) -> str:
    """ล้างคำลงท้าย ค่ะ/คะ/ครับ/จ้ะ ที่เล็ดลอดมา (LLM ไม่ทำตาม prompt 100%) —
    "นะคะ" ถูกตัดทั้งคำ ส่วน "นะ" เดี่ยวๆ ที่ไม่มีคำลงท้ายตามหลังคงไว้"""
    out = _PARTICLE_RE.sub("", text)
    out = _NA_RE.sub("", out)
    return _drop_space_before_punct(out)


_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def _has_stray_latin(text: str, prompt: str) -> bool:
    """มีคำอังกฤษในคำตอบที่ไม่ได้มาจากคำถาม/ข้อมูลอ้างอิง (ถือว่าเพี้ยน)"""
    allowed = {w.lower() for w in _LATIN_WORD_RE.findall(prompt)}
    return any(w.lower() not in allowed for w in _LATIN_WORD_RE.findall(text))


def fix_maiyamok(text: str) -> str:
    """ไม้ยมก (ๆ) เว้นวรรคหน้าและหลังเสมอ เช่น "ดีๆ นะ" -> "ดี ๆ นะ"
    (ไม่เว้นหลัง ๆ ถ้าท้ายบรรทัดหรือตามด้วยเครื่องหมายวรรคตอน)"""
    out = re.sub(r"[ \t]{2,}", " ", text)  # ยุบช่องว่างซ้ำก่อน แล้วจับช่องว่างเดี่ยวหน้า ๆ (เลี่ยง regex ที่ backtrack)
    out = re.sub(r"[ \t]?ๆ", " ๆ", out)
    out = re.sub(r"ๆ(?=[^\s!?.,…~)\"'”’ๆ])", "ๆ ", out)
    out = re.sub(r"(?<=ๆ)[ \t]+(?=ๆ)", " ", out)
    out = re.sub(r"^[ \t]+ๆ", "ๆ", out, flags=re.MULTILINE)
    return re.sub(r"[ \t]{2,}", " ", out)


def _strip_markdown(text: str) -> str:
    """
    เผื่อ Gemini แอบใส่ Markdown มาทั้งที่สั่งห้ามแล้วใน system prompt (LLM
    ไม่ได้ทำตามคำสั่งฟอร์แมตได้ 100% เสมอไป) — ล้างสัญลักษณ์ Markdown ที่พบ
    บ่อยที่สุดออกอีกชั้นเป็นตาข่ายนิรภัย ไม่ต้องแก้ prompt ใหม่ทุกครั้งที่เจอ
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **ตัวหนา** -> ตัวหนา
    text = re.sub(r"^[ \t]*[-*•][ \t]+", "", text, flags=re.MULTILINE)  # bullet ต้นบรรทัด
    text = re.sub(r"^[ \t]*\d+\.[ \t]+", "", text, flags=re.MULTILINE)  # 1. 2. 3. ต้นบรรทัด
    text = re.sub(r"^#{1,6}[ \t]+", "", text, flags=re.MULTILINE)  # # หัวข้อ
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)  # เว้นบรรทัดเกินหนึ่งบรรทัด -> หนึ่งบรรทัด
    return text.strip()


# ประวัติการคุยล่าสุด [(คำถาม, คำตอบ), ...] เรียงเก่า→ใหม่ — router ตั้งค่าไว้ต่อ request
# (ContextVar แยกกันต่อ request จึงไม่ปนกันระหว่างผู้ใช้ แม้ GeminiClient ตัวเดียวถูกใช้ร่วมกัน)
conversation_history: ContextVar[list[tuple[str, str]] | None] = ContextVar(
    "conversation_history", default=None
)
MAX_HISTORY_ANSWER_CHARS = 600


def _history_contents() -> list:
    contents = []
    for q, a in conversation_history.get() or []:
        if len(a) > MAX_HISTORY_ANSWER_CHARS:
            a = a[:MAX_HISTORY_ANSWER_CHARS] + "..."
        contents.append(types.Content(role="user", parts=[types.Part(text=q)]))
        contents.append(types.Content(role="model", parts=[types.Part(text=a)]))
    return contents


class QuotaExhaustedError(Exception):
    """โควตารายวันหมด (ไม่ใช่ rate limit ต่อนาที) ของ "ทุกโมเดลในลำดับสำรอง" — retry ไม่ช่วย
    ต้องรอ reset (เที่ยงคืนตามเขตเวลา Google) หรือเปิด billing เท่านั้น"""


# ---------------------------------------------------------------------------------------------
# ตัวช่วยควบคุมต่อ request (ContextVar แยกกันต่อ request จึงไม่ปนกันระหว่างผู้ใช้)
# ---------------------------------------------------------------------------------------------

# ตัวคุมโควตาต่อผู้ใช้ (usage_limit.UsageGuard) — ถ้า None = ไม่จำกัด (เช่น ตอนรัน eval)
usage_guard: ContextVar = ContextVar("usage_guard", default=None)

# อนุญาตให้ "อ่าน" จากแคชไหม — router ตั้งเป็น False เมื่อเป็นคำถามต่อเนื่อง (ต้องอิงบทสนทนาของคนนั้น)
cache_lookup_allowed: ContextVar[bool] = ContextVar("cache_lookup_allowed", default=True)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def configured_models() -> list[str]:
    """ลำดับโมเดลตอบแชท อ่านจาก .env  ANSWER_MODELS=gemini-2.5-flash,gemini-3.5-flash-lite
    ตัวแรกคือโมเดลหลัก ตัวถัดไปคือสำรอง (ใช้เมื่อโมเดลก่อนหน้าโควตาหมดหรือชน rate limit)
    ตั้งเป็นตัวเดียว (เช่น ANSWER_MODELS=gemini-3.5-flash-lite) เพื่อใช้โมเดลเดียวตลอด"""
    raw = os.environ.get("ANSWER_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or [DEFAULT_MODEL, FALLBACK_MODEL]


class AnswerCache:
    """แคชคำตอบในหน่วยความจำ (LRU + หมดอายุ) — คำถามเดิมด้วยข้อมูลอ้างอิงเดิมในวันเดียวกัน
    ได้คำตอบเดิมทันที ไม่เสียโควตา Gemini และตอบเร็วขึ้น

    ความปลอดภัยของข้อมูลผู้ใช้: key คือ prompt เต็ม (รวมข้อมูลเฉพาะบุคคลที่ถูกใส่ในคำถามแล้ว เช่น
    ชื่อ วันเกิด ทะเบียน) + วันที่ จึงชนกันเฉพาะกรณีที่ input เหมือนกันทุกอย่าง และจะ "เก็บ" ลงแคชเฉพาะคำตอบที่
    สร้างตอนไม่มีประวัติการคุยแนบ (ไม่งั้นคำตอบอาจมีเนื้อหาจากบทสนทนาของคนแรกหลุดไปให้คนอื่น)"""

    def __init__(self, max_entries: int = 500, ttl_seconds: float = 12 * 3600):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            stored_at, value = item
            if now - stored_at > self.ttl_seconds:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# ใช้ร่วมกันทั้ง process (GeminiClient มีตัวเดียวอยู่แล้วใน RAG singleton แต่ทำเป็น module-level เผื่อสร้างหลายตัว)
answer_cache = AnswerCache()

# โมเดลที่ถูกพักไว้ชั่วคราว {ชื่อโมเดล: เวลา (time.time) ที่จะกลับมาลองใหม่}
_cooldowns: dict[str, float] = {}
_cooldown_lock = threading.Lock()
PER_DAY_COOLDOWN_SECONDS = 30 * 60  # โควตารายวันหมด: เว้น 30 นาทีค่อยลองโมเดลหลักใหม่ (เผื่อ reset ผ่านไปแล้ว)
PER_MINUTE_COOLDOWN_SECONDS = 20  # ชน rate limit ต่อนาที: เว้นสั้นๆ


def _cooling_down(model: str) -> bool:
    with _cooldown_lock:
        until = _cooldowns.get(model)
        if until is None:
            return False
        if time.time() >= until:
            del _cooldowns[model]
            return False
        return True


def _start_cooldown(model: str, seconds: float) -> None:
    with _cooldown_lock:
        _cooldowns[model] = time.time() + seconds


def reset_runtime_state() -> None:
    """ล้างแคช + การพักโมเดล (ใช้ในเทสต์)"""
    answer_cache.clear()
    with _cooldown_lock:
        _cooldowns.clear()


class _ModelUnavailable(Exception):
    """โมเดลนี้ตอบไม่ได้ตอนนี้ (โควตาหมด/rate limit/เซิร์ฟเวอร์โหลดสูง) → ลองโมเดลถัดไปในลำดับ"""

    def __init__(self, model: str, per_day: bool, original: Exception):
        super().__init__(f"{model}: {original}")
        self.model = model
        self.per_day = per_day
        self.original = original


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        models: list[str] | None = None,
        use_cache: bool | None = None,
    ):
        """model/models: ระบุโมเดลเอง (ใช้ใน eval ที่ต้องการโมเดลเดียวคงที่ ไม่สลับสำรอง)
        ไม่ระบุ = อ่านลำดับจาก .env (ANSWER_MODELS) หรือค่าเริ่มต้น [2.5-flash, 3.5-flash-lite]
        use_cache: None = ตามค่า ANSWER_CACHE ใน .env (เปิดเป็นค่าเริ่มต้น)"""
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "ไม่พบ GEMINI_API_KEY กรุณาตั้งค่า environment variable "
                "หรือส่ง api_key เข้ามาตอนสร้าง GeminiClient"
            )
        self.client = genai.Client(api_key=api_key)
        self._fixed_models = [model] if model else (list(models) if models else None)
        self._use_cache = use_cache
        self.last_model: str | None = None  # โมเดลที่ตอบคำถามล่าสุด (ไว้ log/ตรวจสอบ)
        self.last_from_cache = False
        self._no_thinking_config: set[str] = set()  # โมเดลที่ไม่รับ thinking_budget (ตรวจพบตอนใช้จริง)

    @property
    def model(self) -> str:
        """โมเดลหลัก (เข้ากันได้กับโค้ดเดิมที่อ่าน gemini.model)"""
        return (self._fixed_models or configured_models())[0]

    def _models(self) -> list[str]:
        return self._fixed_models or configured_models()

    def _cache_enabled(self) -> bool:
        if self._use_cache is not None:
            return self._use_cache
        return _env_flag("ANSWER_CACHE", True)

    @staticmethod
    def _cache_key(prompt: str) -> str:
        from ..usage_limit import today_bangkok  # import ในฟังก์ชันกัน circular import

        return hashlib.sha256(f"{today_bangkok().isoformat()}\n{prompt}".encode("utf-8")).hexdigest()

    def answer(self, question: str, context_chunks: list[str]) -> str:
        """สร้างคำตอบจากคำถาม + context ที่ retrieve มา

        ลำดับ: (1) แคช → (2) เช็คโควตาต่อผู้ใช้ → (3) ลองโมเดลหลัก ถ้าโควตาหมด/ชน rate limit/503
        ให้สลับไปโมเดลสำรองทันทีแทนที่จะให้ผู้ใช้รอหรือเห็น error"""
        context_block = "\n\n---\n\n".join(context_chunks)
        prompt = f"ข้อมูลอ้างอิง:\n{context_block}\n\nคำถาม: {question}"

        history = conversation_history.get()
        cache_on = self._cache_enabled()
        key = self._cache_key(prompt) if cache_on else None

        self.last_from_cache = False
        if key and cache_lookup_allowed.get():
            cached = answer_cache.get(key)
            if cached is not None:
                self.last_from_cache = True
                return cached

        guard = usage_guard.get()
        if guard is not None:
            guard.before()  # โยน DailyLimitExceeded ถ้าครบเพดานแล้ว

        self._bad_thai = False
        text = self._generate_with_fallback(prompt)
        if _has_stray_latin(text, prompt) or self._bad_thai:
            # โมเดลบางครั้งพิมพ์คำอังกฤษเพี้ยนแทรกกลางประโยคไทย (เช่น "ขยับ in ตัวดี") หรือสระ/วรรณยุกต์
            # ซ้อนผิดหลัก (เช่น "ตะ๋") — ลองใหม่ 1 ครั้ง ถ้ารอบสองสะอาดกว่าก็ใช้รอบสอง
            self._bad_thai = False
            retry = self._generate_with_fallback(prompt)
            if not _has_stray_latin(retry, prompt) and not self._bad_thai:
                text = retry

        if guard is not None:
            guard.after()
        if key and not history:
            answer_cache.set(key, text)
        return text

    # -- ภายใน ---------------------------------------------------------------------------------

    def _generate_with_fallback(self, prompt: str) -> str:
        models = self._models()
        # โมเดลที่กำลังพักอยู่ข้ามไปก่อน แต่ถ้าทุกตัวพักหมดก็ลองทุกตัวอีกรอบ (ดีกว่าไม่ตอบเลย)
        candidates = [m for m in models if not _cooling_down(m)] or models

        last_error: _ModelUnavailable | None = None
        all_per_day = True
        for model in candidates:
            try:
                text = self._call_model(model, prompt)
                self.last_model = model
                return text
            except _ModelUnavailable as e:
                last_error = e
                all_per_day = all_per_day and e.per_day
                _start_cooldown(model, PER_DAY_COOLDOWN_SECONDS if e.per_day else PER_MINUTE_COOLDOWN_SECONDS)

        assert last_error is not None
        if all_per_day:
            raise QuotaExhaustedError(
                f"โควตารายวันของโมเดล {', '.join(candidates)} หมดแล้ว — รอ reset รอบถัดไป "
                "(เที่ยงคืนตามเขตเวลา Google) หรือเปิด billing เพื่อเพิ่มโควตา"
            ) from last_error.original
        raise last_error.original

    def _config(self, model: str) -> types.GenerateContentConfig:
        kwargs = {
            "system_instruction": SYSTEM_PROMPT,
            # 0.3 เดิมทำให้คำตอบดวงประจำวัน/ดวงราศีออกมาเหมือนท่องข้อมูล
            # อ้างอิงตรงๆ ทุกครั้ง (deterministic เกินไปสำหรับงานเรียบเรียง
            # เชิงสร้างสรรค์) ขยับขึ้นมาให้มีสีสัน/ถ้อยคำที่หลากหลายขึ้น
            # โดยยังคุมด้วย system prompt ที่ห้ามแต่งข้อมูลนอกเหนือ reference
            # อยู่แล้ว จึงไม่กระทบความถูกต้องของเนื้อหา
            # โมเดลสำรอง (flash-lite) เล็กกว่า สุ่มคำเพี้ยนง่ายเมื่อ temperature สูง จึงลดลง
            "temperature": 0.8 if model == DEFAULT_MODEL else 0.5,
        }
        if model not in self._no_thinking_config:
            # gemini-2.5-flash "คิด" (thinking) ก่อนตอบเป็นค่าเริ่มต้น ทำให้ช้าขึ้น
            # หลายวินาที งานนี้เป็นการเรียบเรียงจากข้อมูลอ้างอิงที่ให้ไว้ ไม่ต้องใช้
            # การคิดเชิงลึก ปิดไว้เพื่อให้ตอบเร็วขึ้นมาก
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    def _call_model(self, model: str, prompt: str) -> str:
        """เรียกโมเดลเดียว: retry เฉพาะ 503 (เซิร์ฟเวอร์โหลดสูงชั่วคราว) ส่วน 429 สลับโมเดลทันที"""
        contents = _history_contents() + [types.Content(role="user", parts=[types.Part(text=prompt)])]
        for attempt in range(MAX_RETRIES + 1):  # +1 เผื่อรอบที่ใช้ลองใหม่เพราะโมเดลไม่รับ thinking_budget
            try:
                response = self.client.models.generate_content(
                    model=model, contents=contents, config=self._config(model)
                )
                raw = response.text
                if thai_text.has_invalid_thai(raw):
                    self._bad_thai = True  # ให้ชั้น answer() ลองใหม่ 1 ครั้ง
                    raw = thai_text.clean_invalid_thai(raw)
                return thai_text.add_word_breaks(fix_maiyamok(strip_particles(_strip_markdown(raw))))
            except (errors.ClientError, errors.ServerError) as e:
                code = getattr(e, "code", None)
                message = str(e)
                if code == 400 and model not in self._no_thinking_config:
                    # โมเดลรุ่นใหม่บางตัว (เช่น gemini-3.5-flash-lite) ไม่รับ thinking_budget=0 และ Google ตอบแค่
                    # "400 INVALID_ARGUMENT" ทั่วไปโดยไม่บอกว่าผิดตรงไหน → ลองใหม่โดยไม่ส่งค่านี้ 1 ครั้ง (จำไว้ไม่ลองซ้ำ)
                    # ถ้าลองใหม่แล้วยัง 400 อยู่ = ปัญหาอื่น จะโยน error ออกไปตามปกติ
                    self._no_thinking_config.add(model)
                    continue
                if code == 429:
                    raise _ModelUnavailable(model, per_day="PerDay" in message, original=e) from e
                if code == 503:
                    if attempt >= MAX_RETRIES - 1:
                        raise _ModelUnavailable(model, per_day=False, original=e) from e
                    time.sleep(3 * (attempt + 1))  # 3s แล้ว 6s
                    continue
                raise
        raise RuntimeError("generate ไม่สำเร็จหลังลองซ้ำครบจำนวนแล้ว")  # ไม่ควรมาถึงบรรทัดนี้
