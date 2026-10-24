"""
models.py
---------
ตาราง:
- users               ข้อมูลบัญชีผู้ใช้ (สิ่งที่กรอกในหน้า login/register ของ Flutter)
- user_astro_profiles ผลคำนวณดวง (ราศี/ปีนักษัตร) — คำนวณจาก birth_date อัตโนมัติ
                       ไม่ให้ผู้ใช้กรอกเอง ตามที่ตกลงไว้ (ดู zodiac.py)
- otp_codes           รหัส OTP ทางอีเมล (สมัครสมาชิก/ตั้งรหัสผ่านใหม่) — เก็บเฉพาะ hash
- chat_messages       ประวัติการสนทนากับ RAG (หน้าแชท) ต่อผู้ใช้ 1 คน — เก็บ
                       ต่อเนื่องเป็นไทม์ไลน์เดียว ไม่ได้แบ่งเป็นหลาย session
                       แยกกัน (ตรงกับ UX ปัจจุบันของ chat_screen.dart ที่มี
                       บทสนทนาต่อเนื่องเดียว ไม่มีแนวคิด "เริ่มแชทใหม่")
- history_entries    ประวัติคำทำนายต่อผู้ใช้ (หน้า "ประวัติ") — คำตอบแชท ดวงประจำวัน เลขศาสตร์
                       ชื่อ/เบอร์/ทะเบียน มีสถานะ "บันทึกไว้" (is_saved) ซิงก์ข้ามเครื่องได้
- shirt_colors        เนื้อหา "เสื้อสีมงคล" ต่อวันในสัปดาห์ — จัดการผ่านหน้าเว็บ
                       แอดมิน (admin/index.html) ไม่ใช่ผู้ใช้ทั่วไปกรอกเอง
- sacred_places       เนื้อหาสถานที่สิ่งศักดิ์สิทธิ์ — จัดการผ่านหน้าเว็บแอดมิน
                       เช่นกัน (คนละส่วนกับข้อมูลผู้ใช้/แชทด้านบน)

หนึ่ง user มีได้ profile เดียว (one-to-one) เผื่ออนาคตอยากเก็บผลคำนวณ
เพิ่มเติม (เช่น ตำแหน่งดาวตอนเกิด) แยกออกจากตาราง users หลักไว้ก่อน
"""

from datetime import datetime
from .timeutil import utcnow

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    # NULL = บัญชีที่สมัครด้วย Google/Facebook และยังไม่เคยตั้งรหัสผ่าน (ตั้งได้ทีหลัง
    # ผ่าน "ลืมรหัสผ่าน" ซึ่งยืนยันด้วย OTP อีเมล) — authenticate_user ต้องเช็คก่อนใช้เสมอ
    password_hash = Column(String(255), nullable=True)
    # id ของผู้ใช้ฝั่ง provider ("sub" ของ Google / "id" ของ Facebook) ใช้จับคู่ตอน
    # login ครั้งต่อไปแทนการเทียบอีเมลอย่างเดียว (อีเมลเปลี่ยนได้ แต่ id คงที่)
    google_id = Column(String(64), unique=True, index=True, nullable=True)
    facebook_id = Column(String(64), unique=True, index=True, nullable=True)

    birth_date = Column(Date, nullable=False)
    # NULL = ไม่ทราบเวลาเกิด (ตรงกับ checkbox "ไม่ทราบเวลาเกิด" ในหน้า signup)
    # มีผลต่อความแม่นยำของ zodiac_sign จริงๆ เพราะสูตรสุริยยาตร์อิงเวลาด้วย
    # (ดู zodiac.py) ถ้า NULL ระบบจะ fallback ไปใช้เที่ยงวันแทนตอนคำนวณ
    birth_time = Column(Time, nullable=True)
    # ตรงกับ toggle "ซ่อนปีเกิด" ในหน้า signup ของแอป (แสดงผลอย่างเดียว ไม่กระทบการคำนวณ)
    hide_birth_year = Column(Boolean, default=False, nullable=False)

    # ชื่อไฟล์รูปโปรไฟล์ใน uploads/avatars/ (ดู app/avatars.py) — NULL = ยังไม่ตั้งรูป
    avatar_path = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    astro_profile = relationship(
        "UserAstroProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    chat_messages = relationship(
        "ChatMessage", back_populates="user", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )

    @property
    def avatar_url(self) -> str | None:
        """path สัมพัทธ์ (แอปเอาไปต่อกับ baseUrl เอง) — NULL ถ้ายังไม่มีรูป"""
        return f"/uploads/avatars/{self.avatar_path}" if self.avatar_path else None


class UserAstroProfile(Base):
    __tablename__ = "user_astro_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    zodiac_sign = Column(String(20), nullable=False)  # ราศี เช่น "กันย์"
    zodiac_animal = Column(String(20), nullable=False)  # ปีนักษัตร เช่น "มะเมีย"

    calculated_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="astro_profile")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    role = Column(String(20), nullable=False)  # "user" หรือ "assistant"
    content = Column(Text, nullable=False)
    # เก็บ sources (list ของ {id, title, score}) เป็น JSON string — มีแค่ฝั่ง
    # assistant เท่านั้นที่มีค่า ฝั่ง user เป็น NULL เสมอ
    sources = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="chat_messages")


class HistoryEntry(Base):
    """1 แถว = 1 คำทำนายในหน้าประวัติ แยกจาก chat_messages ตั้งใจ: กด "เริ่มแชทใหม่"
    (ล้าง chat_messages) แล้วประวัติและรายการที่บันทึกไว้ยังอยู่
    kind: chat | daily | name | number
    category: daily | zodiac | numerology | color | general
    ref_key: ใช้กันซ้ำ เช่น "daily:2026-10-09" (วันละ 1 แถว) "number:5กก1555" — NULL = ไม่กันซ้ำ"""

    __tablename__ = "history_entries"
    __table_args__ = (UniqueConstraint("user_id", "ref_key", name="uq_history_user_ref"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    category = Column(String(20), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    summary = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    is_saved = Column(Boolean, default=False, nullable=False)
    ref_key = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)


class OtpCode(Base):
    """รหัส OTP 6 หลักที่ส่งทางอีเมล — เก็บเฉพาะ hash (HMAC) ไม่เก็บรหัสจริง
    purpose: "signup" (ยืนยันอีเมลตอนสมัคร) หรือ "reset" (ตั้งรหัสผ่านใหม่)
    1 แถว = 1 ครั้งที่ส่ง; ขอใหม่ = แถวเก่าถูก mark used ทันที"""

    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    purpose = Column(String(20), nullable=False)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class DailyColorChart(Base):
    """สีมงคลประจำวันตามหลักจีน (ธาตุ/หยินหยาง) — ผูกกับ "ปี+เดือน+วันที่จริง"
    (year, month, day_of_month) ไม่ใช่วันซ้ำทุกปีแบบเดิม เพราะธาตุประจำวันและ
    วันในสัปดาห์จริงเปลี่ยนไปตามปีจริง (คำนวณวันในสัปดาห์จาก year/month/day ได้เอง
    ตอนแสดงผล ไม่ต้องเก็บซ้ำ) ต้นทางข้อมูลมักเป็นตารางที่ประกาศใหม่ทุกเดือน
    (เช่น เครดิต "PasutAstro" ในตัวอย่างที่ผู้ใช้ส่งมา) จึงต้องกรอกใหม่ทุกเดือน

    แต่ละหมวดสี (help/love/luck/problem) เก็บเป็นข้อความอิสระ (เช่น "ดำ, น้ำเงินเข้ม"
    หรือมีเครื่องหมาย ** ต่อท้ายสีที่ต้องระวังเป็นพิเศษ) แทนที่จะแยกเป็นสีละฟิลด์
    เพราะจำนวนสีต่อหมวดไม่คงที่ และง่ายกว่ามากตอนกรอกข้อมูลจากตารางต้นฉบับ"""

    __tablename__ = "daily_color_charts"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True)  # ปี ค.ศ.
    month = Column(Integer, nullable=False, index=True)  # 1 (ม.ค.) - 12 (ธ.ค.)
    day_of_month = Column(Integer, nullable=False, index=True)  # 1-31

    element_name = Column(String(50), nullable=True)  # ธาตุ เช่น "ดิน หยาง"
    help_colors = Column(String(255), nullable=True)  # ได้รับความช่วยเหลือ
    love_colors = Column(String(255), nullable=True)  # ส่งเสริมความรัก/มิตรภาพ
    luck_colors = Column(String(255), nullable=True)  # ให้โชคลาภ/ความสำเร็จ
    problem_colors = Column(String(255), nullable=True)  # ปัญหาและอุปสรรค (สีที่ควรเลี่ยง)
    zodiac_note = Column(String(255), nullable=True)  # ภาคกิจกรรม/กลุ่มปีนักษัตรที่เกี่ยวข้อง (ไม่บังคับ)
    source_note = Column(String(255), nullable=True)  # ที่มาของข้อมูล เช่น "cr. PasutAstro"

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SacredPlace(Base):
    """สถานที่สิ่งศักดิ์สิทธิ์ (วัด/ศาลเจ้า/เทวสถาน ฯลฯ) — ขอบเขตเริ่มต้นตามที่ระบุใน
    proposal ICT01 คือกรุงเทพฯ แต่ province เก็บเป็นข้อความอิสระ เผื่อขยายพื้นที่
    ภายหลังโดยไม่ต้องแก้โครงสร้างตาราง"""

    __tablename__ = "sacred_places"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    category = Column(String(50), nullable=True)  # เช่น "วัด", "ศาลเจ้า", "เทวสถาน"
    province = Column(String(100), default="กรุงเทพมหานคร", nullable=False)
    district = Column(String(100), nullable=True)  # เขต/อำเภอ
    highlight = Column(String(255), nullable=True)  # สิ่งศักดิ์สิทธิ์/จุดเด่นสั้นๆ เช่น "พระพรหมเอราวัณ"
    description = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    image_url = Column(String(500), nullable=True)
    source_note = Column(Text, nullable=True)  # ที่มาของข้อมูล/หมายเหตุอ้างอิง

    # รายละเอียดแยกหมวด (เพิ่ม ต.ค. 2026) — ฟิลด์ข้อความหลายบรรทัดใช้ "1 บรรทัด = 1 รายการ"
    # และบรรทัดอาจเขียนเป็น "หัวข้อ | รายละเอียด" (หัวข้อไม่บังคับ) แอปจะใส่เลขลำดับให้เอง
    travel_info = Column(Text, nullable=True)  # วิธีเดินทาง
    worship_steps = Column(Text, nullable=True)  # ลำดับการไหว้/สักการะ (เรียงตามบรรทัด)
    offerings = Column(Text, nullable=True)  # ของไหว้/ของถวาย
    etiquette = Column(Text, nullable=True)  # ข้อควรปฏิบัติ/การแต่งกาย
    opening_hours = Column(String(255), nullable=True)  # วัน-เวลาเปิด
    best_time = Column(String(255), nullable=True)  # ช่วงเวลาที่นิยมไป/เหมาะไป
    wish_tags = Column(String(255), nullable=True)  # ขอพรเรื่อง คั่นด้วยจุลภาค เช่น "ความรัก,การงาน"
    chants = Column(Text, nullable=True)  # บทสวด/คาถา เก็บเป็น JSON list: [{"title","text","note"}]

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class DeityArticle(Base):
    """บทความองค์เทพ/บทสวดในคลังบทความของแอป — แอดมินเพิ่ม/แก้ผ่านหน้าเว็บ /admin/
    (เพิ่ม ต.ค. 2026) แอปจะรวมกับบทความที่ฝังในเครื่อง (hindu_deity_articles.dart)
    โดยบทความที่ slug ซ้ำกับของในเครื่องจะไม่ถูกแสดงซ้ำ"""

    __tablename__ = "deity_articles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(80), nullable=False, unique=True, index=True)  # รหัสบทความ เช่น hindu-ganga
    title = Column(String(200), nullable=False)  # ชื่อไทย เช่น พระแม่คงคา
    subtitle = Column(String(300), nullable=True)  # "Ganga Devi • เทวีแห่งสายน้ำ" (ส่วนก่อน • = ชื่อสากล)
    summary = Column(Text, nullable=True)  # สรุปสั้นแสดงในรายการ
    topics = Column(String(255), nullable=True)  # หัวข้อ คั่นจุลภาค: wisdom,wealth,love,success,protection,change
    image_url = Column(String(500), nullable=True)  # ลิงก์รูปภาพ (ไม่ใส่ = ใช้ไอคอน)
    sections = Column(Text, nullable=True)  # JSON list: [{"heading","body"}]
    mantra = Column(String(500), nullable=True)  # บทสวดสั้น (ใส่เมื่อมีแหล่งอ้างอิงเท่านั้น)
    mantra_note = Column(String(500), nullable=True)
    source_note = Column(Text, nullable=True)  # ที่มาของข้อมูล (เก็บฝั่งแอดมิน ไม่โชว์ในแอป)
    is_published = Column(Boolean, default=True, nullable=False)  # false = ฉบับร่าง ไม่แสดงในแอป
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
