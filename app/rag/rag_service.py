"""
rag_service.py
---------------
รวม retriever_chroma.py + gemini_client.py เป็น RAG pipeline เดียว
ย้ายมาจาก sai_mu_rag/main.py เดิม (ตัดส่วน CLI/interactive loop ออก
เพราะตอนนี้ใช้งานผ่าน FastAPI endpoint แทน — ดู app/routers/chat.py)
"""

from __future__ import annotations

import re
from datetime import date

from .. import name_suggest, car_color, daily_engine, daily_fortune, number_luck, number_meanings, numerology, suriyayart, taksa, transit
from .gemini_client import GeminiClient
from .retriever_chroma import ChromaRetriever

# คำที่ใช้จับ "เจตนา" ว่าผู้ใช้กำลังถามดวงประจำวัน/สัปดาห์/เดือน (ไม่ใช่คำถามทั่วไป)
# เช็คแบบ "มีคำว่า 'ดวง' + คำบอกช่วงเวลาใดคำหนึ่ง" อยู่ในประโยคเดียวกัน โดยไม่สนว่า
# คำไหนมาก่อนมาหลัง เพราะภาษาไทยพูดได้ทั้งสองแบบ เช่น "ดวงตอนนี้เป็นไง" กับ
# "ตอนนี้ดวงเป็นไงบ้าง" ความหมายเดียวกันแต่คำละตำแหน่ง — ถ้าเช็คแบบวลีตายตัวจะจับ
# ได้ไม่ครบ (เคยพลาดเคส "ตอนนี้ดวงเป็นไงบ้าง" มาแล้ว)
DAILY_HOROSCOPE_TIME_WORDS = [
    "วันนี้", "ตอนนี้", "ช่วงนี้", "สัปดาห์นี้", "เดือนนี้",
    "ประจำวัน", "ประจำสัปดาห์", "ประจำเดือน",
]


def is_today_report_question(question: str) -> bool:
    """ถามดวง "วันนี้" (ดวงรวม หรือเจาะหมวด เช่น "ความรักวันนี้เป็นไง") — ใช้ตัวคำนวณ
    ดวงรายวันหลายหมวด (daily_engine) ตอบแทนการดึง chunk ทั่วไป"""
    q = question.replace(" ", "")
    if "วันนี้" not in q and "ประจำวัน" not in q:
        return False
    return "ดวง" in q or daily_engine.detect_focus(q) is not None


LONG_RANGE_WORDS = ("ปีหน้า", "ปีนี้", "เดือนหน้า", "เดือนนี้", "อนาคต", "ปีไหน", "เมื่อไหร่", "เมื่อไร", "ตลอดชีวิต", "อีกกี่ปี", "สัปดาห์หน้า", "พรุ่งนี้", "ปี 25", "ปี25")


def is_current_topic_question(question: str) -> bool:
    """คำถามเจาะหมวดแบบทั่วไป/ช่วงนี้ (เช่น "ดวงคนมีแฟนเป็นยังไง") ที่ตอบจากผลคำนวณ
    ของวันนี้ได้ — ข้ามถ้าถามช่วงยาว (ปีหน้า/อนาคต/เมื่อไหร่ ฯลฯ) เพราะเครื่องคำนวณรู้แค่วันนี้"""
    q = question.replace(" ", "")
    if any(w in q for w in LONG_RANGE_WORDS):
        return False
    return daily_engine.detect_focus(q) is not None


def is_daily_horoscope_question(question: str) -> bool:
    """เช็คว่าคำถามนี้เข้าข่าย "ดวงวันนี้/ประจำช่วงเวลา" ไหม — ต้องมีคำว่า "ดวง" และมี
    คำบอกช่วงเวลาคำใดคำหนึ่งอยู่ในประโยคเดียวกัน ไม่สนลำดับก่อนหลัง (ตัดช่องว่างออก
    ก่อนเทียบด้วย กันกรณีผู้ใช้พิมพ์เว้นวรรคแปลกๆ เช่น "ดวง วันนี้")"""
    q = question.replace(" ", "")
    if "ดวง" not in q:
        return False
    return any(w in q for w in DAILY_HOROSCOPE_TIME_WORDS)


# chunk สองโดเมนนี้ถูกกันไม่ให้หลุดเข้ามาในการค้นหาแบบทั่วไป (ask()) เพราะเนื้อหา
# พูดถึง "ความรัก"/"การงาน" บ่อยจนไปแย่งอันดับกับ chunk เลขศาสตร์ที่ถามเรื่องเดียวกัน
# ทั้งที่ผู้ใช้ไม่ได้ถามเรื่องราศี/ทักษาเลย — ต้องเข้าถึงผ่านการดึงด้วย id ตรงๆ เท่านั้น
GENERIC_SEARCH_EXCLUDE_DOMAINS = ["zodiac_trait", "taksa_day"]


def extract_named_zodiac_sign(question: str) -> str | None:
    """เช็คว่าคำถามเอ่ยชื่อราศีใดราศีหนึ่งตรงๆ ไหม (เช่น "ราศีตุลย์นิสัยเป็นไง")
    คืนชื่อราศีนั้นถ้าเจอ — ใช้แทนที่การพึ่ง semantic search หา chunk zodiac-*
    เพราะตอนนี้ chunk กลุ่มนี้ถูกกันออกจากการค้นหาทั่วไปแล้ว (ดู
    GENERIC_SEARCH_EXCLUDE_DOMAINS) จึงต้องตรวจจับชื่อราศีแล้วดึงด้วย id ตรงๆ แทน"""
    for rasi in suriyayart.RASI_NAMES:
        if rasi in question:
            return rasi
    return None


def is_generic_zodiac_question(question: str) -> bool:
    """เช็คว่าเป็นคำถาม "ดวงตามราศี" แบบไม่เจาะจงราศีไหน (เช่น "ราศีของฉันนิสัยเป็นไง")
    ซึ่งต้องรู้ว่าผู้ใช้เป็นราศีอะไรก่อนถึงจะตอบได้ตรงตัว — ถ้าคำถามเอ่ยชื่อราศีใดราศี
    หนึ่งอยู่แล้ว ให้ไปใช้ extract_named_zodiac_sign() แทน (แยกกันคนละกรณี)"""
    if is_daily_horoscope_question(question):
        return False
    if "ราศี" not in question:
        return False
    if extract_named_zodiac_sign(question):
        return False
    return True


DAILY_COLOR_KEYWORDS = ["สีมงคล", "สีเสื้อ", "เสื้อสีมงคล", "สีเสริมดวง", "ใส่สีอะไร", "ใส่สีไหน"]


def is_daily_color_question(question: str) -> bool:
    """เช็คว่าคำถามนี้ถามเรื่อง "สีมงคล/สีเสื้อประจำวัน" ไหม — ถ้าใช่ ต้องตอบด้วย
    ข้อมูลจริงจากตาราง daily_color_charts (ที่แอดมินกรอกผ่านหน้าเว็บ /admin/)
    ไม่ใช่ปล่อยให้ค้นหาแบบ semantic search ทั่วไปใน ask() เพราะ ChromaDB ไม่มี
    ข้อมูลสีมงคลจริงของแต่ละวันอยู่เลย (ข้อมูลนี้อยู่ใน SQL table คนละตัว) —
    ก่อนหน้านี้คำถามแบบนี้หลุดไปตอบแบบทั่วไปที่ไม่ตรงกับข้อมูลจริง"""
    return any(kw in question for kw in DAILY_COLOR_KEYWORDS)


DAILY_LUCKY_NUMBER_KEYWORDS = ["เลขมงคล", "เลขนำโชค", "เลขโชคดี", "เลขเด็ด", "เลขนำโชค"]
DAILY_TIME_WORDS = ["วันนี้", "ประจำวัน", "ตอนนี้", "วันนี้เลย"]


def is_daily_lucky_number_question(question: str) -> bool:
    """ถามเลขนำโชคประจำวัน (เช่น "เลขมงคลวันนี้") — ต้องมีทั้งคำว่าเลขมงคล/เลขนำโชค และคำบอก
    ว่าเป็นของวันนี้ เพื่อไม่ไปแย่งคำถามเลขศาสตร์อื่น (เช่น เลขมงคลของเบอร์โทร/ชื่อ) ซึ่งมี
    branch ของตัวเองอยู่แล้ว เลขชุดนี้คำนวณจริงจากวันนี้ + วันเกิด (ชุดเดียวกับการ์ดเสี่ยงทายในแอป)"""
    return any(k in question for k in DAILY_LUCKY_NUMBER_KEYWORDS) and any(
        t in question for t in DAILY_TIME_WORDS
    )


FOLLOW_UP_STARTERS = ("แล้ว", "ถ้า", "งั้น", "ส่วน", "แต่", "อีก", "ต่อ", "ทำไม", "เพราะอะไร", "แปลว่า", "หมายความ")
FOLLOW_UP_WORDS = ("อันนี้", "อันนั้น", "เรื่องนี้", "เรื่องนั้น", "ตัวนี้", "ตัวนั้น", "แบบนี้", "แบบนั้น", "ที่บอก", "ที่ว่า", "ข้างต้น")


def is_follow_up_question(question: str) -> bool:
    """คำถามสั้นๆ ที่ต่อจากเรื่องก่อนหน้า เช่น "แล้วควรเอาสีไหนดีคะ" — ไม่มีหัวข้อของตัวเอง
    ต้องอาศัยคำถาม/คำตอบก่อนหน้าถึงจะเข้าใจ (ระบบเดิมตอบทีละข้อความแยกกันไม่มีบริบท)"""
    q = question.strip()
    if len(q) > 45:
        return False
    return q.startswith(FOLLOW_UP_STARTERS) or any(w in q for w in FOLLOW_UP_WORDS)


# ข้อความที่มีคำของหัวข้อใหม่ชัดเจน — แม้จะขึ้นต้นว่า "แล้ว..." ก็ไม่ผูกกับทะเบียน/เบอร์ของเรื่องก่อนหน้า
# (Gemini ยังเห็นประวัติและตัดสินเองได้ว่าเกี่ยวข้องไหม)
OWN_TOPIC_WORDS = ("ดวง", "ราศี", "วันนี้", "สีมงคล", "เลขมงคล", "เลขนำโชค", "ชื่อ", "ความรัก", "การงาน", "การเงิน")


def build_follow_up_note(prev_question: str, prev_answer: str) -> str:
    """ข้อความบริบทที่ต่อท้ายคำถามต่อเนื่องก่อนส่งให้ Gemini (ย่อคำตอบเก่าไม่ให้ยาวเกิน)"""
    prev_a = prev_answer.strip().replace("\n", " ")
    if len(prev_a) > 500:
        prev_a = prev_a[:500] + "..."
    return (
        f"\n\n(บริบทจากการคุยก่อนหน้า: ผู้ใช้เพิ่งถามว่า \"{prev_question.strip()}\" และได้คำตอบสรุปว่า "
        f"\"{prev_a}\" — คำถามนี้ถามต่อเนื่องจากเรื่องนั้น ให้ตอบโดยเชื่อมกับเรื่องก่อนหน้า "
        f"เช่น ทะเบียน เลข ชื่อ หรือสีที่เพิ่งพูดถึง ไม่ต้องทวนเรื่องเดิมยาวๆ)"
    )


def is_car_color_question(question: str) -> bool:
    """ถามเรื่องสีรถ (เช่น "สีรถอะไรเหมาะกับฉัน", "รถสีขาวดีไหม") — ตอบจากตำราสีรถตามวันเกิด
    (car_color.py) ไม่ใช่ semantic search หรือสีมงคลประจำวัน"""
    return "สีรถ" in question or ("รถ" in question and "สี" in question)


def is_ambiguous_fortune_question(question: str) -> bool:
    """เช็คว่าเป็นคำถาม "ดวง" กว้างๆ ที่ไม่ได้ระบุว่าจะเอาระบบไหน (เช่น "ดวงความรัก
    ของฉัน", "ดวงการงานฉันเป็นไง") — แอปนี้มี "ดวง" สองระบบซ้อนกันอยู่ (เลขศาสตร์
    กับโหราศาสตร์ราศี) คำถามแบบนี้ไม่ได้เอ่ยทั้งราศีและเลขอะไรเลย จึงตอบทั้งสองมุม
    รวมกันในคำตอบเดียว แทนที่จะเดาว่าผู้ใช้หมายถึงระบบไหนระบบเดียว
    (คำถามที่ระบุชัดแล้ว เช่น มีคำว่า "ราศี" หรือเป็นคำถามดวงประจำวัน/ประจำเวลา จะถูก
    กรองออกไปตั้งแต่ก่อนเรียกฟังก์ชันนี้อยู่แล้ว)"""
    if is_daily_horoscope_question(question):
        return False
    if "ราศี" in question:
        return False
    if extract_named_zodiac_sign(question):
        return False
    return "ดวง" in question


# ---------------------------------------------------------------------
# กลไกปฏิเสธคำถามนอกขอบเขต (out-of-scope refusal)
# ---------------------------------------------------------------------
# ใช้เช็คเฉพาะใน NumerologyRAG.ask() (ทางตอบทั่วไปที่พึ่ง semantic search) เท่านั้น
# เพราะทุกทางตอบอื่น (ดวงประจำวัน/ราศี/ทักษา/เลขเบอร์โทร ฯลฯ) ถูกกรองเข้ามาแล้วด้วย
# การจับคำสำคัญเฉพาะทางของตัวเอง จึง "อยู่ในขอบเขต" โดยธรรมชาติอยู่แล้ว ไม่ต้องเช็คซ้ำ
#
# ทำงาน 2 ชั้น:
#   1) เช็คคำสำคัญที่บ่งบอกว่าเกี่ยวกับศาสตร์ที่แอปนี้รองรับ (เลขศาสตร์/โหราศาสตร์/
#      ทักษา/มูเตลูทั่วไป) ก่อน — ถ้าเจอคำใดคำหนึ่ง ถือว่าอยู่ในขอบเขตทันที ไม่ต้องเช็ค
#      ต่อ (เร็ว ไม่ต้องเรียก embedding API)
#   2) ถ้าไม่เจอคำสำคัญเลย ค่อย fallback ไปเช็คว่าผลการค้นหาแบบ semantic search ที่
#      ใกล้เคียงที่สุด (similarity score จาก ChromaRetriever.retrieve ซึ่งคำนวณจาก
#      1 - cosine_distance อยู่แล้ว) สูงพอไหม — ถ้าต่ำกว่าเกณฑ์ แปลว่าฐานข้อมูลไม่มี
#      อะไรเกี่ยวข้องกับคำถามนี้เลยจริงๆ จึงตอบปฏิเสธแทนที่จะปล่อยให้ Gemini พยายาม
#      ตอบจากข้อมูลที่ไม่เกี่ยวข้องกันคนละเรื่อง (เช่นถามสูตรอาหาร/การเมือง/ข่าวทั่วไป)
#
# ⚠️ หมายเหตุสำคัญที่ต้องแจ้งผู้ใช้: SCOPE_SIMILARITY_THRESHOLD ด้านล่างเป็นค่า
# ประมาณการเท่านั้น ยังไม่เคยได้ทดสอบจริงกับ Gemini embedding API (sandbox นี้ไม่มี
# GEMINI_API_KEY ให้เรียกจริง) แนะนำให้ทดลองถามคำถามนอกขอบเขตหลายๆ แบบกับคำถามใน
# ขอบเขตหลายๆ แบบ แล้วดู similarity score จริงจาก log ก่อนปรับค่านี้ให้เหมาะสมอีกที
# (ค่ายิ่งสูง ยิ่งเข้มงวด/ปฏิเสธง่ายขึ้น แต่เสี่ยงปฏิเสธคำถามในขอบเขตที่ถามแปลกๆ ไปด้วย)
IN_SCOPE_KEYWORDS = [
    "เลข", "ราศี", "ดวง", "ทักษา", "ชื่อมงคล", "โหราศาสตร์", "ภพ", "ดาว", "มุม",
    "กาลกิณี", "มูเตลู", "ฤกษ์", "สีมงคล", "นักษัตร", "ปีเกิด", "วันเกิด", "เบอร์",
    "ทะเบียน", "องค์เทพ", "ไหว้", "บูชา", "เทวดา", "พระ", "สิ่งศักดิ์สิทธิ์", "โชค",
    "ดวงชะตา",
    # คำเฉพาะเจาะจงชื่อเทพฮินดู — เพิ่มหลังผู้ใช้ขอฟีเจอร์ "คลังบทความ" เรื่องการ
    # บูชาเทพฮินดู เผื่อผู้ใช้ถามชื่อเทพตรงๆ โดยไม่มีคำทั่วไปอย่าง "ไหว้"/"บูชา" ปนมาด้วย
    "พิฆเนศ", "ตรีมูรติ", "ลักษมี", "สรัสวดี", "อุมาเทวี", "ปารวตี", "กาลี",
    "พรหม", "วิษณุ", "ศิวะ", "เทพฮินดู", "ฮินดู", "เทพปกรณัม",
] + list(transit.TOPIC_KEYWORDS_TO_HOUSE.keys())
# ต่อท้ายด้วยคำหัวข้อชีวิตทั้งหมดจาก transit.TOPIC_KEYWORDS_TO_HOUSE (ความรัก/งาน/
# การเงิน/สุขภาพ ฯลฯ) ด้วย — เพราะพบว่าคำถามธรรมชาติแบบ "งานช่วงนี้เป็นไงบ้าง" หรือ
# "ความรักฉันจะเป็นไง" ไม่มีคำว่า "ดวง" เลย ถ้าไม่เพิ่มคำเหล่านี้เข้ามา กลไกปฏิเสธคำถาม
# นอกขอบเขตด้านล่างอาจเข้าใจผิดว่าเป็นคำถามนอกขอบเขตทั้งที่จริงๆ อยู่ในขอบเขตแอปเต็มๆ
# (ใช้ list(...) ดึงจาก dict เดียวกับที่ transit.py ใช้จับหัวข้อจริง เพื่อไม่ต้องคอย
# sync คำสองที่ให้ตรงกันเอง)

SCOPE_SIMILARITY_THRESHOLD = 0.5

OUT_OF_SCOPE_MESSAGE = (
    "ขอโทษด้วยนะ คำถามนี้อยู่นอกเหนือขอบเขตที่น้องมูตอบได้ \n\n"
    "แอปนี้เชี่ยวชาญเฉพาะเรื่องเลขศาสตร์ (เบอร์โทร/ทะเบียนรถ/ชื่อ) โหราศาสตร์ไทย "
    "(ดวงราศี ดวงประจำวัน) และทักษาปกรณ์ (ชื่อมงคลตามวันเกิด) เท่านั้น ลองถาม"
    "เกี่ยวกับเรื่องเหล่านี้กับน้องมูดูนะคะ"
)


def is_in_scope_by_keyword(question: str) -> bool:
    """เช็คชั้นที่ 1 (เร็ว ไม่ต้องเรียก embedding API): มีคำสำคัญที่บ่งบอกว่าเกี่ยวกับ
    ศาสตร์ที่แอปนี้รองรับอยู่ในคำถามไหม"""
    return any(kw in question for kw in IN_SCOPE_KEYWORDS)


# เกณฑ์สัมพัทธ์: เก็บเฉพาะ chunk ที่คะแนนไม่ต่ำกว่าอันดับ 1 เกินค่านี้ (ตัด chunk
# ข้างเคียงที่ไม่เกี่ยว เช่น "เลข 5" แล้วได้ number-55 ติดมา) — ที่มา: eval_retrieval.py
# (delta sweep: δ=0.04 ได้ NDCG 0.949, Recall 0.90, เฉลี่ย 1.7 chunk) ปรับได้ตามผลวัดล่าสุด ตั้งเป็น None เพื่อปิด
RELATIVE_SCORE_MARGIN = 0.04

# ถามเลขเดี่ยวๆ ชัดเจน เช่น "เลข 8", "ได้เลข 62" — ไม่เอาเลขที่ต่อกับตัวเลขอื่น
# (เบอร์โทร/ทะเบียน ถูกแยกไปทางอื่นใน chat.py ก่อนมาถึงนี่แล้ว) มีแค่ number-0..100
_EXPLICIT_NUMBER_RE = re.compile(r"เลข\s*(\d{1,3})(?!\d)")


def extract_explicit_numbers(question: str, max_items: int = 2) -> list[int]:
    """คืนเลข 0-100 ที่ระบุตรงๆ หลังคำว่า "เลข" ตามลำดับที่ปรากฏ (ไม่ซ้ำ)"""
    out: list[int] = []
    for m in _EXPLICIT_NUMBER_RE.finditer(question):
        n = int(m.group(1))
        if 0 <= n <= 100 and n not in out:
            out.append(n)
    return out[:max_items]


class NumerologyRAG:
    def __init__(self, top_k: int = 4):
        self.retriever = ChromaRetriever()
        self.gemini = GeminiClient()
        self.top_k = top_k

    def ask_daily_color(self, question: str, color_row) -> dict:
        """ตอบคำถามสีมงคล/สีเสื้อประจำวัน โดยใช้ข้อมูลจริงจากตาราง
        daily_color_charts (ดึงมาให้แล้วจาก router ก่อนเรียกฟังก์ชันนี้ เพราะ
        NumerologyRAG ไม่ถือ DB session ของตัวเอง) — ไม่ใช้ semantic search เลย
        เพราะ ChromaDB ไม่มีข้อมูลสีมงคลจริงของแต่ละวันอยู่ (ข้อมูลนี้แอดมินกรอก
        ผ่านหน้าเว็บ /admin/ ลง SQL table คนละตัว อัปเดตใหม่ทุกเดือน)
        color_row เป็น None ถ้ายังไม่มีใครกรอกข้อมูลของวันนี้ไว้เลย"""
        if color_row is None:
            answer = (
                "ขออภัย ตอนนี้ยังไม่มีข้อมูลสีมงคลประจำวันของวันนี้ในระบบ "
                "(แอดมินอาจยังไม่ได้อัปเดตข้อมูลของเดือนนี้) ลองถามใหม่อีกครั้งภายหลังนะ"
            )
            return {"answer": answer, "sources": []}

        facts = (
            f"วันที่ {color_row.day_of_month}/{color_row.month}/{color_row.year}, "
            f"ธาตุประจำวัน: {color_row.element_name or 'ไม่ระบุ'}, "
            f"สีที่ช่วยเหลือ/เกื้อหนุน: {color_row.help_colors or 'ไม่ระบุ'}, "
            f"สีเสริมความรัก/มิตรภาพ: {color_row.love_colors or 'ไม่ระบุ'}, "
            f"สีเสริมโชคลาภ/ความสำเร็จ: {color_row.luck_colors or 'ไม่ระบุ'}, "
            f"สีที่ควรระวัง (เสี่ยงปัญหา/อุปสรรค): {color_row.problem_colors or 'ไม่ระบุ'}"
        )
        if color_row.zodiac_note:
            facts += f", หมายเหตุเพิ่มเติม: {color_row.zodiac_note}"

        tailored_question = (
            f"{question}\n\n"
            f"(ข้อมูลจริงจากระบบสำหรับวันนี้: {facts} — ช่วยเรียบเรียงเป็นคำตอบที่เป็น"
            f"ธรรมชาติ สุภาพ แนะนำสีเสื้อ/สิ่งของให้ผู้ใช้ตามข้อมูลนี้เท่านั้น ห้ามเติมสี"
            f"หรือข้อมูลอื่นที่ไม่ได้ให้มาข้างต้นเด็ดขาด และห้ามใช้โทนบังคับเด็ดขาดแบบ "
            f"'ต้องใส่สีนี้เท่านั้น' ให้ใช้โทนแนะนำแบบยืดหยุ่น เช่น 'วันนี้สีที่ช่วยเสริม"
            f"ดวงคือ...' แทน)"
        )
        answer = self.gemini.answer(tailored_question, [])
        return {"answer": answer, "sources": []}

    def ask_car_color(self, question: str, facts: str) -> dict:
        """ตอบเรื่องสีรถตามตำราสีรถประจำวันเกิด (ข้อมูลจาก car_color.facts_text) — ให้ Gemini
        เรียบเรียงเท่านั้น ห้ามเพิ่มสีหรือเปลี่ยนภูมิที่ระบบคำนวณมาให้"""
        tailored_question = (
            f"{question}\n\n(ข้อมูลจริงจากระบบสีรถ ใช้ตามนี้เท่านั้น ห้ามเพิ่มหรือเปลี่ยนสี ภูมิ หรือตัวเลข:\n"
            f"{facts}\n"
            f"วิธีตอบ: ถ้าผู้ใช้ถามสีรถที่ควรเลือก ให้แนะนำ 2-3 กลุ่มสีที่เหมาะกับเป้าหมายของเขา (เช่น อยากเสริมเงินทอง "
            f"ให้ดูภูมิมูลละ อยากเสริมโชคลาภให้ดูภูมิศรี) และเตือนสีกาลกิณีสั้นๆ ถ้าผู้ใช้ถามสีใดสีหนึ่ง ให้ตอบตรงๆ ก่อนว่า"
            f"ใช้ได้หรือควรเลี่ยง แล้วบอกเหตุผลจากภูมิ ไม่ต้องไล่ทุกภูมิ พูดภาษาง่ายๆ ไม่ใช้ศัพท์ภูมิทักษาโดยไม่อธิบาย "
            f"บอกว่าเป็นความเชื่อทางโหราศาสตร์ไทย ให้เลือกตามความสบายใจได้ ไม่ต้องกลัวถ้าสีรถเป็นกาลกิณี ผู้ใช้เกิดวันตามที่ระบุในข้อมูลแน่นอน ให้พูดว่า \"คุณเกิดวัน...\" ห้ามพูดว่า \"ถ้าเกิดวัน...\" และห้ามใช้คำว่า ตำรา และถ้าข้อมูลมีเรื่อง"
            f"ช่วงอายุหรือเลขทะเบียนที่ควรเลี่ยง ให้พูดถึงสั้นๆ เมื่อเกี่ยวกับคำถาม)"
        )
        answer = self.gemini.answer(tailored_question, [])
        return {
            "answer": answer,
            "sources": [{"id": "car-color-guide", "title": car_color.SOURCE_TITLE, "score": 1.0}],
        }

    def ask_daily_lucky_numbers(self, question: str, birth_date: date | None) -> dict:
        """ตอบเลขมงคล/เลขนำโชคของวันนี้ ด้วยเลขที่คำนวณจริง (daily_fortune.lucky_numbers —
        ชุดเดียวกับที่โชว์ในการ์ดเสี่ยงทายบนหน้าหลัก) ไม่ใช้ semantic search เพราะ ChromaDB
        ไม่มีข้อมูลเลขประจำวัน และห้ามให้ Gemini แต่งเลขเอง"""
        today = date.today()
        weekday_name = daily_fortune.WEEKDAY_NAMES[today.weekday()]
        weekday_no = daily_fortune.WEEKDAY_NUMBER[today.weekday()]
        date_no = daily_fortune.digit_root(daily_fortune._digit_sum(today))
        if birth_date:
            numbers = daily_fortune.lucky_numbers(today, birth_date)
            personal_no = daily_fortune.digit_root(
                daily_fortune._digit_sum(birth_date) + daily_fortune._digit_sum(today)
            )
            basis = (
                f"เลขประจำวัน{weekday_name} = {weekday_no}, เลขรวมของวันที่วันนี้ = {date_no}, "
                f"เลขส่วนตัวของผู้ใช้ (คำนวณจากวันเกิดรวมกับวันนี้) = {personal_no}"
            )
        else:
            numbers = [n for n in dict.fromkeys([weekday_no, date_no]) if n]
            basis = f"เลขประจำวัน{weekday_name} = {weekday_no}, เลขรวมของวันที่วันนี้ = {date_no}"
        tailored_question = (
            f"{question}\n\n"
            f"(ข้อมูลจริงจากระบบสำหรับวันนี้ {today.strftime('%d/%m/%Y')}: เลขนำโชคของวันนี้คือ "
            f"{', '.join(str(n) for n in numbers)} ที่มาของเลข: {basis} — ช่วยบอกเลขเหล่านี้"
            f"พร้อมอธิบายสั้นๆ ว่าเลขแต่ละตัวมาจากอะไร ห้ามเติมเลขอื่นที่ไม่ได้ให้มา ห้ามอ้างว่า"
            f"รับประกันโชคหรือถูกรางวัล ให้พูดเป็นแนวทางเสริมกำลังใจแบบยืดหยุ่น)"
        )
        answer = self.gemini.answer(tailored_question, [])
        return {"answer": answer, "sources": []}

    def ask_daily_report(self, question: str, zodiac_sign: str, birth_date: date, birth_time=None, general: bool = False) -> dict:
        """ดวงวันนี้แบบหลายหมวดจากผลคำนวณจริง (daily_engine) — LLM เรียบเรียงเท่านั้น
        ไม่แต่งข้อมูลเพิ่ม ผลชุดเดียวกับการ์ดดวงในแอป"""
        today = daily_fortune.today_thai()
        try:
            report = daily_engine.build_daily_report(
                zodiac_sign=zodiac_sign, birth_date=birth_date, today=today, birth_time=birth_time
            )
        except Exception:  # noqa: BLE001 — ข้อมูลราศีเก่า/พัง: ถอยไปวิธีเดิม
            return self.ask_daily_horoscope(question, zodiac_sign)

        focus = daily_engine.detect_focus(question.replace(" ", ""))
        facts = daily_engine.facts_text(report, focus)
        if focus:
            label = dict(daily_engine.CATEGORIES)[focus]
            how = (
                f"ผู้ใช้ถามเรื่อง{label} ให้ตอบเป็น 4 ย่อหน้า รวมประมาณ 9-12 ประโยค เว้นบรรทัดว่างระหว่างย่อหน้า ไม่ใช้หัวข้อหรือสัญลักษณ์ "
                f"ย่อหน้าแรกตอบตรงๆ ว่าเรื่องนี้ตอนนี้ดีหรือควรระวัง ย่อหน้าที่สองเล่าให้เห็นภาพในชีวิตจริงว่าความรู้สึกหรือสถานการณ์ที่มักเจอเป็นอย่างไร "
                f"ย่อหน้าที่สามบอกสิ่งที่ควรระวังในเรื่องนี้ โดยใช้ข้อมูลของหมวดนี้และปัจจัยพิเศษของวันที่เกี่ยวข้องกับเรื่องที่ถามเท่านั้น "
                f"ย่อหน้าสุดท้ายให้คำแนะนำที่ทำได้จริง 1-2 ข้อ "
                f"ห้ามพูดถึงเรื่องอื่นที่ผู้ใช้ไม่ได้ถาม (เช่น ถามเรื่องความรักห้ามพูดเรื่องงาน ครอบครัว หรือเพื่อน) "
                f"ถ้าข้อมูลมีไม่พอสำหรับบางย่อหน้า ให้ตัดย่อหน้านั้นออก เหลือ 2-3 ย่อหน้าก็ได้ ไม่ต้องแต่งเพิ่ม"
            )
        else:
            how = (
                "ผู้ใช้ถามดวงวันนี้โดยรวม ให้ตอบสั้นๆ เป็น 3 ย่อหน้า รวมประมาณ 5-7 ประโยค เว้นบรรทัดว่างระหว่างย่อหน้า ไม่ใช้หัวข้อหรือสัญลักษณ์ "
                "ย่อหน้าแรกภาพรวมของวัน ย่อหน้าที่สองเรื่องที่เด่นที่สุดวันนี้ ย่อหน้าที่สามเรื่องที่ควรระวัง "
                "ถ้าไม่มีเรื่องที่ควรระวังให้ตัดย่อหน้านี้ออก ห้ามพูดถึงหมวดที่กลางๆ และห้ามไล่ครบทุกหมวด "
                "เว้นแต่ผู้ใช้จะถามเจาะจงเอง"
            )
        if general:
            how += (
                " คำถามนี้ไม่ได้ระบุว่าวันนี้ ให้เล่าว่าตอนนี้/ช่วงนี้ดวงเรื่องนี้เป็นอย่างไร โดยอ้างจากข้อมูลวันนี้"
                " ไม่ต้องพูดถึงอนาคตระยะยาว และถ้าผู้ใช้ถามเหมือนมีแฟนอยู่แล้ว ให้เล่าในมุมคนที่มีคู่ และไม่ต้องเดาเรื่องส่วนตัวของแฟน"
            )
        tailored = (
            f"{question}\n\n(คำสั่ง: {how} ใช้เฉพาะข้อมูลที่ให้ไว้ ห้ามเพิ่มเรื่องหรือคำชมที่ไม่มีในข้อมูล "
            f"ห้ามพูดศัพท์เทคนิคตรงๆ เช่น ภพ ทักษา บริวาร เดช ศรี มูละ อุตสาหะ มนตรี กาลกิณี ให้เล่าเป็นภาษาพูดง่ายๆ "
            f"ไม่ต้องบอกคะแนนเป็นตัวเลข ใช้คำว่า ดี กลางๆ หรือควรระวัง แทน และห้ามฟันธงว่าจะเกิดเหตุการณ์แน่นอน "
            f"ห้ามพูดถึง \"ภาพรวมของปี\" หรือ \"ช่วงปีนี้\" เพราะผู้ใช้ถามเรื่องวันนี้ ให้เล่าเฉพาะสิ่งที่เป็นของวันนี้)"
        )
        answer = self.gemini.answer(tailored, [facts])
        sources = [
            {"id": f["key"], "title": " / ".join(f.get("sources", [])), "score": 1.0}
            for f in report["factors"]
        ]
        return {"answer": answer, "sources": sources}

    def ask_daily_horoscope(self, question: str, zodiac_sign: str) -> dict:
        """ตอบคำถามดวงประจำวัน/ช่วงเวลา แบบ "ส่วนตัว" จริงๆ — คำนวณตำแหน่งจันทร์
        เทียบกับราศีกำเนิดของผู้ใช้ (transit.calculate_transit_house) แล้วดึง chunk
        ความหมายของภพนั้นมาตรงๆ ด้วย id (ไม่ใช้ semantic search เพราะคำถามผู้ใช้
        อาจไม่ตรงกับเนื้อหา house-N เลยทางความหมาย) ก่อนส่งให้ Gemini เรียบเรียง
        เป็นคำทำนายที่อ่านลื่นเป็นธรรมชาติ"""
        today = date.today()
        house_no, house_name = transit.calculate_transit_house(zodiac_sign, today)
        chunk_id = f"house-{house_no}"
        chunks = self.retriever.get_by_ids([chunk_id])

        if not chunks:
            # เผื่อกรณี chunks_clean.json บนเซิร์ฟเวอร์ยังไม่ได้อัปเดตเป็นชุดที่มี
            # house-1..12 (เช่น ลืม ingest ใหม่) — ตอบแบบทั่วไปแทนดีกว่าพังไปเลย
            return self.ask(question)

        context_chunks = [c.text for c in chunks]

        # ปัจจัยที่เปลี่ยนทุกวัน + บอกตรงๆ ว่าดวงจันทร์อยู่ภพเดิมมากี่วันแล้ว กันคำตอบ
        # ดูซ้ำกับเมื่อวานโดยไม่รู้สาเหตุ (ภพเดิมอยู่ราว 2-3 วันตามธรรมชาติ)
        stay = daily_fortune.moon_stay_info(zodiac_sign, today)
        weekday_name = daily_fortune.WEEKDAY_NAMES[today.weekday()]
        weekday_color = daily_fortune.WEEKDAY_COLORS[today.weekday()]
        if stay["total_days"] > 1:
            if stay["day_index"] == 1:
                stay_note = (
                    f"วันนี้เป็นวันแรกที่เรื่องนี้เด่น และจะเด่นต่อเนื่องถึงวันที่ "
                    f"{stay['last_day'].strftime('%d/%m')} แล้วค่อยเปลี่ยนไปเรื่องอื่น"
                )
            elif stay["day_index"] < stay["total_days"]:
                stay_note = (
                    f"เรื่องนี้เด่นต่อเนื่องมาตั้งแต่เมื่อวาน (วันนี้เป็นวันที่ {stay['day_index']} "
                    f"จาก {stay['total_days']}) จะเปลี่ยนไปเรื่องอื่นหลังวันที่ "
                    f"{stay['last_day'].strftime('%d/%m')}"
                )
            else:
                stay_note = (
                    f"วันนี้เป็นวันสุดท้ายที่เรื่องนี้เด่น พรุ่งนี้ ({stay['next_change'].strftime('%d/%m')}) "
                    f"จะเปลี่ยนไปเรื่องอื่น"
                )
        else:
            stay_note = "เรื่องนี้เด่นเฉพาะวันนี้ พรุ่งนี้จะเปลี่ยนไปเรื่องอื่น"

        tailored_question = (
            f"{question}\n\n"
            f"(ข้อมูลเพิ่มเติมของวันนี้: เป็นวัน{weekday_name} สีประจำวันคือ{weekday_color} "
            f"{stay_note} — ให้เล่าเรื่องนี้สั้นๆ ในคำตอบด้วยภาษาพูดธรรมดา เพื่อให้ผู้ใช้เข้าใจ"
            f"ว่าทำไมดวงช่วงนี้อาจคล้ายเมื่อวาน และเชื่อมคำแนะนำกับวัน{weekday_name}หรือสี"
            f"{weekday_color}เล็กน้อยให้คำตอบของวันนี้ไม่ซ้ำกับวันอื่น)\n\n"
            f"(ข้อมูลจากการคำนวณจริงของระบบ: วันที่ {today.strftime('%d/%m/%Y')} "
            f"ดวงจันทร์โคจรเข้าสู่ภพที่ {house_no} ({house_name}) นับจากราศีกำเนิด "
            f"{zodiac_sign} ของผู้ใช้คนนี้ — ช่วยเรียบเรียงเป็นคำทำนายดวงประจำวันที่ฟังเป็น"
            f"ธรรมชาติ โดยใช้ 'ความหมายทั่วไปของภพนี้' ในข้อมูลอ้างอิงด้านล่างเป็นคำทำนาย"
            f"หลักได้เลย (ถือว่าดวงจันทร์ผ่านมาที่ภพนี้ทำให้เรื่องราวตามความหมายทั่วไปของภพ"
            f"ถูกกระตุ้น/เด่นขึ้นในวันนี้) ไม่ต้องกล่าวถึงหรือติดใจว่าข้อมูลอ้างอิงมีเฉพาะ"
            f"กรณีดาวอังคาร/พุธ/ดาวอื่นๆ สถิตในภพนี้ ไม่มีข้อมูลของดวงจันทร์โดยตรง — ให้ตอบมั่นใจ"
            f"เหมือนโหรที่ทำนายจากตำแหน่งจันทร์ปกติ ไม่ต้องขึ้นประโยคขอโทษหรือบอกว่าข้อมูลไม่ครบ "
            f"และห้ามพูดศัพท์เทคนิคใดๆ ตรงๆ ทั้ง \"ภพที่ {house_no}\" และชื่อภพภาษาบาลี/สันสกฤต "
            f"(เช่น \"{house_name}\" หรือชื่อภพอื่นอย่างตนุ กฎุมพะ สหัชชะ พันธุ ปุตตะ อริ ปัตนิ "
            f"มรณะ ศุภะ กัมมะ ลาภะ วินาสนะ) ให้แปลความหมายเป็นภาษาพูดทั่วไปที่คนอ่านเข้าใจ"
            f"ทันทีแทน เช่น พูดว่า \"เรื่องความรักและคู่ครอง\" แทนคำว่า \"ปัตนิ\")"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }

    def ask_daily_horoscope_topic(
        self, question: str, zodiac_sign: str, topic_keyword: str, topic_house_number: int
    ) -> dict:
        """ตอบคำถามดวงช่วงเวลาแบบเจาะจงหัวข้อ (เช่น "ดวงความรักช่วงนี้") — ต่างจาก
        ask_daily_horoscope() ตรงที่ไม่ได้บอกแค่ "วันนี้ดวงจันทร์อยู่ภพไหนโดยรวม"
        (ซึ่งอาจไม่เกี่ยวกับหัวข้อที่ถามเลยก็ได้ เช่นถามเรื่องความรักแต่จันทร์ดันอยู่ภพ
        เรื่องพี่น้อง) แต่คำนวณมุมสัมพันธ์ระหว่างดวงจันทร์ปัจจุบันกับภพของหัวข้อนั้นใน
        ดวงกำเนิดโดยตรง (transit.calculate_topic_transit) ให้ตรงประเด็นที่ถามจริงๆ"""
        today = date.today()
        aspect_name, topic_house_name = transit.calculate_topic_transit(
            zodiac_sign, topic_house_number, today
        )
        chunk_ids = [f"house-{topic_house_number}", "aspect-overview", "aspect-orb-and-thai-method"]
        chunks = self.retriever.get_by_ids(chunk_ids)

        if not chunks:
            # เผื่อ chunks_clean.json บนเซิร์ฟเวอร์ยังไม่มีชุด house-*/aspect-* ครบ
            return self.ask_daily_horoscope(question, zodiac_sign)

        context_chunks = [c.text for c in chunks]

        # มุม "กุม" และ "เล็งตรง" เนื้อหาต้นฉบับ (aspect-overview) ระบุไว้ตรงๆ ว่า "ผลจะดี
        # หรือร้ายขึ้นกับคุณภาพของดาว" ซึ่งระบบไม่ได้คำนวณตำแหน่งดาวเคราะห์ดวงอื่นๆ (คำนวณ
        # แค่อาทิตย์+จันทร์) เลยไม่มีข้อมูลนั้นจริงๆ — ถ้าปล่อยให้ Gemini ทำตามเนื้อหาตรงๆ
        # จะได้คำตอบที่ฟังดูคลุมเครือ ("ขึ้นอยู่กับดวงชะตาของคุณเอง") ซึ่งผู้ใช้จริงรู้สึกว่า
        # ไม่ได้คำตอบอะไรเลย จึงสั่งเพิ่มให้ฟันธงแบบสร้างสรรค์แทน โดยตีความมุมเหล่านี้จาก
        # "ธรรมชาติของมุม" เอง (กุม = พลังรวมศูนย์/เข้มข้นเป็นพิเศษ, เล็งตรง = ดึงดูดและ
        # ตึงเครียดไปพร้อมกัน) ไม่ใช่แต่งข้อมูลดวงดาวที่ไม่มีขึ้นมาเอง
        needs_definitive_framing = aspect_name in ("กุม", "เล็งตรง")
        definitive_instruction = ""
        if needs_definitive_framing:
            definitive_instruction = (
                f" ข้อมูลอ้างอิงเรื่องมุม '{aspect_name}' อาจมีข้อความว่าผลดีหรือร้ายขึ้นกับ"
                f"คุณภาพของดาว ซึ่งระบบไม่มีข้อมูลนั้นให้ ไม่ต้องพูดถึงข้อจำกัดนี้หรือบอกว่า"
                f"'ขึ้นอยู่กับดวงชะตาของคุณเอง' เพราะฟังดูคลุมเครือเกินไป ให้ตีความจาก"
                f"ธรรมชาติของมุมนี้แทน (กุม = พลังเรื่องนี้รวมศูนย์เข้มข้นเป็นพิเศษช่วงนี้ ทั้ง"
                f"โอกาสและความท้าทายจะชัดเจนขึ้นพร้อมกัน, เล็งตรง = มีแรงดึงดูดและความตึง"
                f"เครียดเกิดขึ้นพร้อมกัน ต้องสมดุลให้ดี) แล้วให้คำแนะนำเชิงปฏิบัติที่ชัดเจน"
                f"เป็นรูปธรรมว่าควรวางตัวหรือทำใจอย่างไรกับเรื่อง{topic_keyword}ช่วงนี้ แทนที่"
                f"จะบอกแค่ว่า 'ผลจะดีหรือไม่ดีขึ้นอยู่กับปัจจัยอื่น'"
            )

        tailored_question = (
            f"{question}\n\n"
            f"(ข้อมูลจากการคำนวณจริงของระบบ: วันที่ {today.strftime('%d/%m/%Y')} ดวงจันทร์"
            f"ทำมุม '{aspect_name}' กับตำแหน่งภพ{topic_house_name} (ภพที่เกี่ยวกับเรื่อง"
            f"{topic_keyword}) ในดวงกำเนิดของผู้ใช้คนนี้ — ช่วยเรียบเรียงเป็นคำทำนายเรื่อง"
            f"{topic_keyword}ช่วงนี้ที่ฟังเป็นธรรมชาติ โดยอิงความหมายของภพนี้และความหมาย"
            f"ของมุม '{aspect_name}' จากข้อมูลอ้างอิงด้านล่างประกอบกัน ตอบมั่นใจเหมือนโหร"
            f"ที่ทำนายจริง ไม่ต้องขึ้นประโยคขอโทษหรือบอกว่าข้อมูลไม่ครบ และห้ามพูดศัพท์เทคนิค"
            f"ตรงๆ ทั้ง \"ภพที่ {topic_house_number}\" ชื่อภพภาษาบาลี/สันสกฤต (เช่น "
            f"\"{topic_house_name}\" หรือชื่อภพอื่นอย่างตนุ กฎุมพะ สหัชชะ พันธุ ปุตตะ อริ ปัตนิ "
            f"มรณะ ศุภะ กัมมะ ลาภะ วินาสนะ) และชื่อมุมสัมพันธ์ (เช่น \"{aspect_name}\") "
            f"ให้แปลความหมายเป็นภาษาพูดทั่วไปที่คนอ่านเข้าใจทันทีแทน{definitive_instruction})"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }

    def ask_zodiac_traits(self, question: str, zodiac_sign: str) -> dict:
        """ตอบคำถาม "ดวงตามราศี" แบบไม่เจาะจง (เช่น "ราศีของฉันนิสัยเป็นไง") โดยดึง
        chunk นิสัย/จุดเด่นจุดด้อยของราศีที่ผู้ใช้เกิดมาตรงๆ ด้วย id แทนการเดาจาก
        semantic search (เพราะคำถามแบบนี้มักไม่มีชื่อราศีอยู่ในคำถามเลย)"""
        chunk_id = f"zodiac-{zodiac_sign}"
        chunks = self.retriever.get_by_ids([chunk_id])

        if not chunks:
            # เผื่อ chunks_clean.json บนเซิร์ฟเวอร์ยังไม่มีชุด zodiac-* (ลืม ingest ใหม่)
            return self.ask(question)

        context_chunks = [c.text for c in chunks]
        tailored_question = (
            f"{question}\n\n"
            f"(ผู้ใช้คนนี้เกิดราศี{zodiac_sign} ช่วยตอบโดยอิงข้อมูลนิสัย จุดเด่นจุดด้อย "
            f"การงาน และความรัก ของราศี{zodiac_sign}จากข้อมูลอ้างอิงด้านล่างโดยตรง พูดใน"
            f"ลักษณะที่เข้าใจง่ายเหมือนกำลังอธิบายให้เจ้าของราศีฟัง ไม่ต้องถามกลับว่าเป็น"
            f"ราศีอะไร เพราะรู้อยู่แล้ว)"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }

    def ask_combined(self, question: str, zodiac_sign: str) -> dict:
        """ตอบคำถาม "ดวง" กว้างๆ ที่ไม่ได้ระบุระบบ (เช่น "ดวงความรักของฉัน")

        ตอนแรกออกแบบให้ผสมเนื้อหาเลขศาสตร์เข้ามาด้วย แต่พบว่าเลขศาสตร์ของแอปนี้เป็น
        "ความหมายของเลข" แบบดั้งเดิม (ใช้เช็คเบอร์โทร/ทะเบียนรถ ฯลฯ) ไม่ใช่เลขที่ผูก
        กับตัวผู้ใช้เลย ระบบไม่มีทางรู้ว่า "เลขของผู้ใช้" คือเลขอะไร ถ้าดึงมาปนจะได้เลข
        แบบสุ่มจาก semantic search ที่บังเอิญพูดเรื่องเดียวกัน (เช่น "ความรัก") มาเสนอ
        ราวกับเป็นเลขของผู้ใช้ ซึ่งเข้าใจผิดได้ — จึงตัดส่วนเลขศาสตร์ออก เหลือแค่มุมราศี
        ซึ่งเป็นข้อมูลเดียวที่ผูกกับตัวผู้ใช้จริงๆ โดยไม่ต้องขอข้อมูลเพิ่ม (เทียบเท่ากับ
        ask_zodiac_traits แต่เก็บเป็นเมธอดแยกไว้เผื่ออนาคตอยากต่อยอด เช่น ถ้าผู้ใช้เคย
        ให้เบอร์โทร/ทะเบียนรถไว้ในโปรไฟล์ ค่อยดึงเลขศาสตร์ที่แท้จริงของผู้ใช้กลับมาใส่ตรงนี้ได้)
        """
        return self.ask_zodiac_traits(question, zodiac_sign)

    def ask_name_check(self, question: str, name: str, birth_date) -> dict:
        """ตอบคำถามเช็คชื่อมงคลตามระบบทักษาปกรณ์ — คำนวณจริงว่าอักษรตัวแรกของชื่อที่
        ถามมา ตกหมวดไหนของวันเกิดผู้ใช้ (app/taksa.py) แล้วดึง chunk อธิบายระบบ +
        ตารางหมวดของวันเกิดนั้นมาให้ Gemini เรียบเรียงเป็นคำตอบที่เข้าใจง่าย"""
        result = taksa.check_name_first_letter(name, birth_date)
        day_index = taksa.get_thai_day_index(birth_date)
        chunks = self.retriever.get_by_ids(["taksa-overview"])

        if not chunks:
            return self.ask(question)

        # ตารางหมวดของวันเกิดสร้างจากโค้ด (taksa.day_table_text) ให้ตรงกับการคำนวณเสมอ
        context_chunks = [taksa.day_table_text(day_index)] + [c.text for c in chunks]
        category = result["category"]
        if category:
            calc_summary = (
                f"ชื่อ '{name}' ขึ้นต้นด้วยอักษร '{result['first_letter']}' ผู้ใช้เกิดวัน"
                f"{result['day_name']} ซึ่งอักษรนี้จัดอยู่ในหมวด '{category['name']}' "
                f"({category['meaning']}) ตามระบบทักษา"
            )
            if result["is_kalakin"]:
                calc_summary += " — หมวดนี้คือกาลกิณี ถือว่าไม่เป็นมงคลสำหรับคนเกิดวันนี้"
        else:
            calc_summary = (
                f"อักษร '{result['first_letter']}' ในชื่อ '{name}' ไม่สามารถระบุหมวดทักษา"
                f"ได้ (อาจไม่ใช่พยัญชนะไทยที่รองรับ เช่น เป็นอักษรภาษาอื่นหรือสระลอย)"
            )

        tailored_question = (
            f"{question}\n\n"
            f"(ผลการคำนวณจริงจากระบบ: {calc_summary} — ช่วยอธิบายให้ผู้ใช้เข้าใจง่ายๆ "
            f"ว่าชื่อนี้เป็นมงคลสำหรับวันเกิดของตัวเองไหม โดยอิงความหมายของหมวดนี้จากข้อมูล"
            f"อ้างอิงด้านล่างประกอบด้วย ถ้าหมวดเป็นกาลกิณีให้บอกตรงๆ อย่างสุภาพว่าไม่ค่อย"
            f"แนะนำและเพราะอะไร ถ้าเป็นหมวดอื่นให้บอกว่าดีอย่างไรตามความหมายของหมวดนั้น)"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }

    def ask_name_suggest(self, question: str, birth_date=None) -> dict:
        """แนะนำชื่อ 3-4 ชื่อ — คัดชื่อด้วยโค้ด (เลี่ยงกาลกิณีตามวันเกิด + เช็คเลขศาสตร์)
        แล้วให้ Gemini เรียบเรียงเป็นภาษาพูด ไม่ให้คิดชื่อเพิ่มเอง"""
        day_index = name_suggest.extract_day_index(question)
        if day_index is None and birth_date:
            day_index = taksa.get_thai_day_index(birth_date)
        if day_index is None:
            return {
                "answer": "อยากให้ช่วยคิดชื่อให้คนเกิดวันอะไรดีคะ บอกวันเกิด (เช่น วันอังคาร) และเป็นชื่อผู้ชายหรือผู้หญิง แล้วจะช่วยคัดมาให้ 3-4 ชื่อเลย",
                "sources": [],
            }
        names = name_suggest.suggest_names(day_index, name_suggest.extract_gender(question))
        if not names:
            return self.ask(question)
        facts = name_suggest.facts_text(day_index, names)
        tailored = (
            f"{question}\n\n(ให้แนะนำเฉพาะชื่อที่อยู่ในรายการข้อมูลอ้างอิงนี้เท่านั้น ห้ามคิดชื่ออื่นเพิ่ม "
            f"บอกความหมายของแต่ละชื่อสั้นๆ และบอกว่าอักษรต้นชื่อไม่ตรงกับหมวดกาลกิณีของวันเกิด "
            f"ตอบเป็นภาษาพูดธรรมดา ไม่ใช้เครื่องหมายมาร์กดาวน์ และปิดท้ายว่าถ้าอยากให้เช็คชื่อเต็มรวมนามสกุลก็ส่งมาได้)"
        )
        answer = self.gemini.answer(tailored, [facts])
        return {"answer": answer, "sources": []}

    def ask_birthdate_numerology(self, question: str, birth_date) -> dict:
        """ตอบคำถามเลขศาสตร์วันเกิด — ดึง birth_date ที่ผู้ใช้กรอกไว้ตอนสมัครสมาชิก
        มาคำนวณตรงๆ (numerology.calculate_birthdate_number) โดยไม่ต้องให้ผู้ใช้พิมพ์
        วันเดือนปีเกิดซ้ำในแชท แล้วดึงความหมายจาก chunk number-{n} ชุดเดียวกับเลขชื่อ/
        เบอร์โทร (เป็นความหมายเลขระบบเดียวกันทั้งหมด)"""
        result = numerology.calculate_birthdate_number(birth_date)
        chunk_id = f"number-{result['final_number']}"
        chunks = self.retriever.get_by_ids([chunk_id])

        if not chunks:
            return self.ask(question)

        context_chunks = [c.text for c in chunks]
        calc_summary = (
            f"วันเกิดของผู้ใช้คนนี้ (จากโปรไฟล์ที่กรอกไว้ตอนสมัครสมาชิก) คือ "
            f"{birth_date.strftime('%d/%m')}/{birth_date.year + 543} (พ.ศ.) เมื่อรวม"
            f"ตัวเลขทุกหลักของวันเดือนปีเกิดเข้าด้วยกันตามหลักเลขศาสตร์ ได้ผลรวม "
            f"{result['raw_total']}"
        )
        if result["raw_total"] != result["final_number"]:
            calc_summary += f" ลดทอนเหลือเลข {result['final_number']}"

        tailored_question = (
            f"{question}\n\n"
            f"(ผลการคำนวณจริงจากระบบ: {calc_summary} — ช่วยอธิบายความหมายของเลข "
            f"{result['final_number']} จากข้อมูลอ้างอิงด้านล่าง โดยเชื่อมโยงว่าเป็น"
            f"เลขศาสตร์ประจำวันเกิดของผู้ใช้คนนี้เอง ให้ฟังเป็นธรรมชาติเหมือนกำลัง"
            f"ทำนายให้เจ้าตัวฟังตรงๆ ไม่ต้องอธิบายวิธีคำนวณทีละขั้นตอน และไม่ต้องถาม"
            f"วันเดือนปีเกิดกลับ เพราะระบบรู้อยู่แล้ว)"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }

    def ask(self, question: str, follow_up_of: tuple[str, str] | None = None) -> dict:
        """follow_up_of = (คำถามก่อนหน้า, คำตอบก่อนหน้า) ถ้าเป็นคำถามต่อเนื่อง — ใช้ค้นข้อมูล
        ด้วยคำถามเดิมรวมกับคำถามใหม่ และแนบบริบทให้ Gemini เชื่อมคำตอบเข้ากับเรื่องเดิม"""
        search_q = f"{follow_up_of[0]} {question}" if follow_up_of else question
        results = self.retriever.retrieve(
            search_q, top_k=self.top_k, exclude_domains=GENERIC_SEARCH_EXCLUDE_DOMAINS
        )

        if not results:
            return {
                "answer": "ขออภัย ไม่พบข้อมูลที่เกี่ยวข้องกับคำถามนี้ในฐานข้อมูล",
                "sources": [],
            }

        # กลไกปฏิเสธคำถามนอกขอบเขต — เช็คแค่ในทางตอบทั่วไปนี้เท่านั้น (ดู
        # is_in_scope_by_keyword ด้านบนไฟล์ว่าทำไม) ชั้นแรกเช็คคำสำคัญก่อน (เร็ว)
        # ถ้าไม่เจอค่อย fallback ไปดู similarity score ของผลลัพธ์ที่ใกล้เคียงที่สุด
        if not is_in_scope_by_keyword(search_q):
            top_score = results[0][1]
            if top_score < SCOPE_SIMILARITY_THRESHOLD:
                return {"answer": OUT_OF_SCOPE_MESSAGE, "sources": []}

        results = self._refine_results(search_q, results)

        context_chunks = [chunk.text for chunk, _ in results]
        answer = self.gemini.answer(question, context_chunks)
        if "OUTOFSCOPE" in answer.replace("_", "").replace(" ", "").upper():
            return {"answer": OUT_OF_SCOPE_MESSAGE, "sources": []}

        return {
            "answer": answer,
            "sources": [
                {"id": chunk.id, "title": chunk.title, "score": round(score, 3)}
                for chunk, score in results
            ],
        }

    def _refine_results(self, question: str, results: list) -> list:
        """ปรับผลค้นก่อนส่งให้ Gemini (ทั้งสองข้อมาจากผลวัดใน eval_retrieval.py):
        1) ถ้าคำถามระบุ "เลข N" ชัดเจน ดึง number-N ตรงๆ มาไว้อันดับแรก — กัน semantic
           search สลับเลขคล้ายกัน (เช่น "เลข 8" ได้ number-80 นำ number-8)
        2) ตัด chunk ที่คะแนนต่ำกว่าอันดับ 1 เกิน RELATIVE_SCORE_MARGIN (เหลืออย่างน้อย 1)"""
        refined = list(results)
        wanted = extract_explicit_numbers(question)
        if wanted:
            direct = self.retriever.get_by_ids([f"number-{n}" for n in wanted])
            order = {f"number-{n}": i for i, n in enumerate(wanted)}
            direct.sort(key=lambda c: order.get(c.id, 99))
            have = {c.id for c in direct}
            refined = [(c, 1.0) for c in direct] + [(c, s) for c, s in refined if c.id not in have]
        if RELATIVE_SCORE_MARGIN is not None and refined:
            top = max(s for _, s in refined)
            refined = [(c, s) for c, s in refined if s >= top - RELATIVE_SCORE_MARGIN] or refined[:1]
        return refined[: max(self.top_k, len(extract_explicit_numbers(question)))]

    def ask_number_sequence(self, question: str, digits: str) -> dict:
        """ตอบคำถามเลขศาสตร์เบอร์โทร/ทะเบียนรถจริง — แยกเลขที่ผู้ใช้ให้มาเป็น "คู่เลข"
        แบบทับซ้อนกัน (numerology.extract_digit_pairs) แล้วดึงความหมายของทุกคู่ (ไม่
        ซ้ำ) มาจาก chunk number-{n} ที่มีอยู่แล้ว (ชุดเดียวกับที่ใช้ตอบ "เลข N หมายถึง
        อะไร" ทั่วไป) ให้ Gemini สังเคราะห์เป็นคำทำนายรวมของเบอร์/ทะเบียนนี้"""
        pairs = numerology.extract_digit_pairs(digits)
        if not pairs:
            return self.ask(question)

        pair_values = numerology.unique_pair_values(pairs)
        chunk_ids = [f"number-{v}" for v in pair_values]
        chunks = self.retriever.get_by_ids(chunk_ids)

        if not chunks:
            return self.ask(question)

        context_chunks = [c.text for c in chunks]
        pairs_display = ", ".join(pairs)
        tailored_question = (
            f"{question}\n\n"
            f"(เลขที่ผู้ใช้ถามถึงคือ '{digits}' เมื่อแยกเป็นคู่เลขทับซ้อนกันตามหลักการ"
            f"ดูเบอร์โทร/ทะเบียนรถ จะได้คู่เลขทั้งหมดคือ: {pairs_display} — ช่วยอ่าน"
            f"ความหมายของแต่ละคู่เลขจากข้อมูลอ้างอิงด้านล่าง แล้วสรุปเป็นคำทำนายรวมของ"
            f"เลขชุดนี้ทั้งหมดให้ฟังเป็นธรรมชาติ บอกทั้งจุดที่ดีและจุดที่ควรระวัง (ถ้ามี) "
            f"ไม่ต้องท่องความหมายของทุกคู่แยกทีละคู่แบบเป็นลิสต์ยาวๆ ให้เรียบเรียงเป็น"
            f"คำอธิบายภาพรวมที่อ่านลื่นแทน)"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }

    def ask_number_luck(
        self,
        question: str,
        number_text: str,
        topic_keyword: str | None = None,
        car_color: str | None = None,
        birth_weekday_color: str | None = None,
        birth_weekday_name: str | None = None,
        car_color_facts: str | None = None,
    ) -> dict:
        """ตอบคำถามเบอร์โทร/ทะเบียนรถ ที่ผูกกับหัวข้อชีวิต (เช่น "เบอร์นี้เรื่องความรักดีไหม")
        หรือสีรถ — คำนวณจริงก่อน: ผลรวมเลข+กลุ่ม (number_luck) และคู่เลขทับซ้อน
        (ความหมายจาก chunk number-N) แล้วให้ Gemini เรียบเรียงโดยเน้นหัวข้อที่ถาม
        สีรถเทียบกับ "สีประจำวันเกิด" ของผู้ใช้เท่านั้น (กติกาง่ายๆ ไม่มีตำราสีรถโดยเฉพาะ)"""
        analysis = number_luck.analyze_number(number_text)
        digits = "".join(ch for ch in analysis["input"] if ch.isdigit())
        pairs = numerology.extract_digit_pairs(digits)
        chunks = self.retriever.get_by_ids([f"number-{v}" for v in numerology.unique_pair_values(pairs)]) if pairs else []

        # ถามเรื่องสี → ดึงเลขหลักเดียวจากผลรวมของทะเบียน/เบอร์นี้ (เช่น 19 → 1) มาอ่าน "สีให้คุณ/สีให้โทษ"
        # ใน chunk ของเลขนั้น แทนการตอบสีของเลขทุกตัวรวมๆ ที่ไม่เกี่ยวกับทะเบียนที่ถาม
        color_root = None
        if "สี" in question and analysis["total"] and not car_color_facts:
            color_root = daily_fortune.digit_root(int(analysis["total"]))
            if color_root:
                have = {c.id for c in chunks}
                chunks = chunks + [
                    c for c in self.retriever.get_by_ids([f"number-{color_root}"]) if c.id not in have
                ]

        facts = [
            f"เลข/ทะเบียนที่ถาม: {analysis['input']}",
            f"ผลรวมตัวเลข{'และอักษร' if analysis['letters'] else ''}ทั้งหมด = {analysis['total']} "
            f"อยู่ใน{number_luck.LEVEL_TEXT[analysis['level']]}"
            if analysis["level"] != "unknown"
            else f"ผลรวมทั้งหมด = {analysis['total']} (ไม่อยู่ในกลุ่มที่ระบบมีข้อมูล ห้ามตีความผลรวมนี้)",
        ]
        meaning = analysis.get("meaning")
        if meaning:
            sum_parts = [f"ความหมายของผลรวม {analysis['total']} ({meaning.get('title', '')}): {meaning.get('overview', '')}"]
            if meaning.get("strengths"):
                sum_parts.append(f"จุดเด่น: {meaning['strengths']}")
            if meaning.get("cautions"):
                sum_parts.append(f"ข้อควรระวัง: {meaning['cautions']}")
            facts.append(" ".join(sum_parts))
        if pairs:
            facts.append("คู่เลขทับซ้อนที่ใช้อ่านความหมาย: " + ", ".join(pairs))
        if color_root:
            facts.append(
                f"ผู้ใช้ถามเรื่องสี — ผลรวมของ {analysis['input']} ย่อเป็นเลข {color_root} ให้แนะนำสีจากส่วน "
                f"'สีให้คุณ' และเตือนสีจากส่วน 'สีให้โทษ' ของเลข {color_root} ในข้อมูลอ้างอิงเท่านั้น ห้ามเอาสีของ"
                f"เลขอื่นมาตอบ บอกสั้นๆ ว่าสีนี้อิงจากเลข {color_root} ของทะเบียน/เบอร์นี้ (เกณฑ์ง่ายๆ ของระบบ) "
                f"ถ้าข้อมูลอ้างอิงไม่ระบุสีของเลขนี้ให้บอกตามตรง"
            )
        elif topic_keyword:
            facts.append(
                f"ผู้ใช้อยากรู้เรื่อง '{topic_keyword}' เป็นหลัก — เลือกอ่านเฉพาะส่วนในความหมายคู่เลข"
                f"ที่เกี่ยวกับเรื่องนี้ ถ้าไม่มีส่วนไหนพูดถึงเรื่องนี้ตรงๆ ให้บอกตามตรงแล้วสรุปจุดเด่นอื่นแทน "
                f"วิธีตอบ: ประโยคแรกของย่อหน้าแรกต้องสรุปตรงๆ ว่าเรื่อง{topic_keyword}ของเลขชุดนี้ \"ดี\" \"ควรระวัง\" หรือ \"มีทั้งสองด้าน\" "
                f"ถ้าข้อมูลของเรื่องนี้มีทั้งข้อดีและข้อควรระวังให้บอกตั้งแต่ประโยคแรกว่าเด่นแบบสองด้าน (เด่นไม่ได้แปลว่าดีอย่างเดียว) "
                f"แล้วค่อยแยกเล่าด้านดีกับด้านที่ควรระวังให้เห็นว่ามาจากคู่เลขไหน ห้ามเล่าแต่ด้านดีก่อนแล้วค่อยมาเตือนทีหลังโดยไม่เกริ่น "
                f"ประโยคปิดท้ายต้องมาจากข้อควรระวังของเรื่อง{topic_keyword}ในคู่เลขที่ให้ไว้เท่านั้น "
                f"ผลรวมของเลขเป็นภาพรวมทั้งชุด ไม่ใช่ของเรื่อง{topic_keyword}โดยเฉพาะ ให้พูดถึงสั้นๆ แยกจากเรื่องที่ถาม"
            )
        else:
            facts.append(
                "ผู้ใช้ถามภาพรวม — เริ่มด้วยการบอกผลรวมกับกลุ่มของเลขชุดนี้ (เช่น \"ผลรวมของทะเบียนนี้คือ 16 อยู่ในกลุ่มกลาง\") "
                "พร้อมความหมายสั้นๆ ของผลรวม แล้วเล่าความหมายของคู่เลขที่ให้ไว้: ถ้ามีไม่เกิน 4 คู่ให้กล่าวถึงครบทุกคู่ "
                "(คู่ที่ความหมายคล้ายกันรวมเป็นประโยคเดียวได้ คู่ละประโยคสั้นๆ ก็พอ) ถ้ามีมากกว่านั้นให้เลือก 3-4 คู่ที่เด่นที่สุด "
                "สุดท้ายสรุปว่าเด่นเรื่องอะไรและควรระวังอะไร"
            )
        if car_color_facts:
            facts.append(
                "ถ้าผู้ใช้ถามเรื่องสีรถ ให้ใช้ข้อมูลสีรถตามวันเกิดนี้เท่านั้น (ไม่ใช้สีของเลขทะเบียน) ผู้ใช้เกิดวันตามที่ระบุแน่นอน พูดว่า \"คุณเกิดวัน...\" ห้ามพูดว่า \"ถ้าเกิดวัน...\" และห้ามใช้คำว่า ตำรา "
                "ตอบเรื่องทะเบียนกับเรื่องสีแยกกันให้ชัด:\n" + car_color_facts
            )
        elif car_color:
            if birth_weekday_color:
                match = "ตรงกับ" if car_color == birth_weekday_color else "ไม่ตรงกับ"
                facts.append(
                    f"สีรถที่ถาม: {car_color} — สีประจำวันเกิด (วัน{birth_weekday_name}) ของผู้ใช้คือ "
                    f"{birth_weekday_color} จึง{match}สีประจำวันเกิด (นี่เป็นเกณฑ์ง่ายๆ ที่ระบบใช้ ไม่ใช่ตำราสีรถ"
                    f"โดยเฉพาะ ให้บอกผู้ใช้ตรงๆ สั้นๆ และอย่าอ้างกฎอื่นเกี่ยวกับสีรถ)"
                )
            else:
                facts.append(
                    f"สีรถที่ถาม: {car_color} — ยังไม่มีวันเกิดผู้ใช้ให้เทียบ ห้ามบอกว่าสีนี้ดีหรือไม่ดี "
                    f"ให้บอกว่าประเมินสีรถไม่ได้เพราะไม่มีวันเกิด"
                )

        tailored_question = (
            f"{question}\n\n(ผลคำนวณจริงจากระบบ ใช้ตามนี้เท่านั้น ห้ามเปลี่ยนตัวเลข:\n- "
            + "\n- ".join(facts)
            + "\nให้ตอบเป็นภาษาพูดธรรมชาติ ไม่ต้องอธิบายวิธีคำนวณ ตามวิธีตอบที่ระบุไว้ข้างบน)"
        )
        # ความหมายคู่เลข: ใช้ number_meanings.json (ภาษาไทยสะอาด) แทนข้อความใน chunk ที่เพี้ยนจากการสกัดไฟล์ต้นฉบับ
        # (สระ/วรรณยุกต์ลอย เช่น "ลกั ษณะ") ซึ่งทำให้โมเดลเขียนคำเพี้ยนตาม — ถ้าไม่มีข้อมูลสะอาดค่อยถอยไปใช้ chunk
        clean_texts: list[str] = []
        for v in numerology.unique_pair_values(pairs) if pairs else []:
            m = number_meanings.get_meaning(v)
            if not m:
                continue
            parts = [f"เลข {v} ({m.get('title', '')}): {m.get('overview', '')}"]
            for label, key in (("จุดเด่น", "strengths"), ("ข้อควรระวัง", "cautions"), ("อาชีพที่เหมาะ", "careers"), ("เพิ่มเติม", "extra")):
                if m.get(key):
                    parts.append(f"{label}: {m[key]}")
            clean_texts.append(" ".join(parts))
        if clean_texts:
            # ถามเรื่องสี: ส่วน "สีให้คุณ/สีให้โทษ" อยู่ใน chunk ดิบของเลขหลักเดียว จึงยังต้องแนบ chunk นั้นไว้
            color_texts = [c.text for c in chunks if color_root and c.id == f"number-{color_root}"]
            context_chunks = clean_texts + color_texts
        else:
            context_chunks = [c.text for c in chunks] or [f"ผลรวมของเลขชุดนี้คือ {analysis['total']}"]
        answer = self.gemini.answer(tailored_question, context_chunks)

        sources = [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks]
        sources.append({"id": "godtowa-sum", "title": "ผลรวมเลข (GODTOWA)", "score": 1.0})
        return {"answer": answer, "sources": sources}

    def ask_name_numerology(self, question: str, name: str) -> dict:
        """ตอบคำถามเลขศาสตร์ชื่อ (ผลรวมตัวอักษรเป็นตัวเลข) — คำนวณจริงด้วย
        numerology.calculate_name_number() แล้วดึงความหมายของเลขผลลัพธ์จาก chunk
        number-{n} ชุดเดียวกับเลขเบอร์โทร/ทะเบียน (เป็นความหมายเลขระบบเดียวกัน)"""
        result = numerology.calculate_name_number(name)
        chunk_id = f"number-{result['final_number']}"
        chunks = self.retriever.get_by_ids([chunk_id])

        if not chunks:
            return self.ask(question)

        context_chunks = [c.text for c in chunks]
        calc_summary = (
            f"ชื่อ '{result['name']}' เมื่อแปลงตัวอักษรแต่ละตัวเป็นตัวเลขตามหลัก"
            f"เลขศาสตร์แล้วรวมกัน ได้ผลรวม {result['raw_total']}"
        )
        if result["raw_total"] != result["final_number"]:
            calc_summary += f" ลดทอนเหลือเลข {result['final_number']}"
        if result["skipped_chars"]:
            calc_summary += (
                f" (มีบางอักษรที่ไม่มีค่ากำหนดในตารางเลขศาสตร์ จึงไม่ถูกนับรวม: "
                f"{', '.join(result['skipped_chars'])})"
            )

        tailored_question = (
            f"{question}\n\n"
            f"(ผลการคำนวณจริงจากระบบ: {calc_summary} — ช่วยอธิบายความหมายของเลข "
            f"{result['final_number']} จากข้อมูลอ้างอิงด้านล่าง โดยเชื่อมโยงว่าเป็น"
            f"ความหมายของชื่อ '{result['name']}' ให้ฟังเป็นธรรมชาติเหมือนกำลังทำนาย"
            f"ชื่อให้เจ้าของฟัง ไม่ต้องอธิบายวิธีคำนวณทีละขั้นตอน)"
        )
        answer = self.gemini.answer(tailored_question, context_chunks)

        return {
            "answer": answer,
            "sources": [{"id": c.id, "title": c.title, "score": 1.0} for c in chunks],
        }
