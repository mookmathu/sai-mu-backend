"""
schemas.py
----------
Pydantic models สำหรับ validate request/response
ตรงกับฟิลด์ที่ฝั่ง Flutter (login_screen.dart / signup_screen.dart) ส่งมาจริง
"""

from datetime import date, datetime, time
from .timeutil import utcnow

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class BirthFields(BaseModel):
    """ข้อมูลวันเกิด — ใช้ร่วมกันทั้งสมัครด้วยอีเมล (RegisterRequest) และสมัครด้วย
    Google/Facebook (SocialCompleteRequest) เพื่อให้กฎ validate ตรงกันเสมอ"""

    birth_day: int = Field(ge=1, le=31)
    birth_month: int = Field(ge=1, le=12)
    birth_year: int
    # ไม่บังคับกรอก — ตรงกับ checkbox "ไม่ทราบเวลาเกิด" ฝั่ง Flutter ที่ปิดช่อง
    # เวลาได้ ถ้าไม่ส่งมา zodiac.py จะ fallback ไปใช้เที่ยงวันแทนตอนคำนวณราศี
    birth_hour: int | None = Field(None, ge=0, le=23)
    birth_minute: int | None = Field(None, ge=0, le=59)
    hide_birth_year: bool = False

    @field_validator("birth_year")
    @classmethod
    def birth_year_reasonable(cls, v: int) -> int:
        current_year = utcnow().year
        if not (current_year - 120 <= v <= current_year):
            raise ValueError("ปีเกิดไม่ถูกต้อง")
        return v

    @model_validator(mode="after")
    def birth_date_exists(self):
        # กันวันที่ที่ไม่มีจริง เช่น 31/02 — เดิมจะหลุดไปพังตอน date(...) ใน crud (500)
        try:
            date(self.birth_year, self.birth_month, self.birth_day)
        except ValueError:
            raise ValueError("วันเกิดไม่ถูกต้อง")
        return self


class RegisterRequest(BirthFields):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    # bcrypt รับรหัสผ่านได้สูงสุด 72 ไบต์ — จำกัดความยาวตัวอักษรไว้ที่ 72
    # เป็นเพดานปลอดภัย (ถ้าใช้อักขระหลายไบต์เช่นภาษาไทยล้วนอาจเกิน 72 ไบต์ได้
    # ก่อน 72 ตัวอักษร แต่กรณีนี้พบน้อยมากสำหรับรหัสผ่าน)
    password: str = Field(min_length=8, max_length=72)
    # OTP 6 หลักที่ได้ทางอีเมลจาก POST /auth/otp/request (purpose="signup")
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OtpRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(pattern=r"^(signup|reset)$")


class OtpRequestResponse(BaseModel):
    message: str
    expires_in: int  # วินาที
    resend_in: int  # วินาที


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResetTokenResponse(BaseModel):
    reset_token: str


class PasswordResetRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=8, max_length=72)


class MessageResponse(BaseModel):
    message: str


class DeleteAccountRequest(BaseModel):
    """ยืนยันการลบบัญชี: บัญชีที่มีรหัสผ่านต้องส่ง password ให้ถูกต้อง
    บัญชี Google/Facebook ที่ยังไม่เคยตั้งรหัสผ่าน ต้องพิมพ์อีเมลของบัญชีให้ตรง (confirm_email)"""

    password: str | None = None
    confirm_email: str | None = None


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=10)


class FacebookLoginRequest(BaseModel):
    access_token: str = Field(min_length=10)


class SocialCompleteRequest(BirthFields):
    registration_token: str
    username: str = Field(min_length=2, max_length=50)
    # ใช้เฉพาะเมื่อ provider ไม่ส่งอีเมลมา (needs_email=True): ผู้ใช้กรอกอีเมลเอง
    # แล้วยืนยันด้วย OTP (purpose=signup) — ผ่านแล้วอีเมลนี้จึงถือว่ายืนยันแล้ว
    email: EmailStr | None = None
    otp_code: str | None = Field(default=None, min_length=6, max_length=6)


class AstroProfileOut(BaseModel):
    zodiac_sign: str
    zodiac_animal: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    birth_date: date
    birth_time: time | None = None
    hide_birth_year: bool
    avatar_url: str | None = None
    astro_profile: AstroProfileOut | None = None

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BirthFields):
    """PATCH /auth/me — แอปส่งค่าทั้งชุดจากหน้า "แก้ไขโปรไฟล์" ทุกครั้ง
    birth_hour/birth_minute ไม่ส่ง (หรือเป็น null) = ไม่ทราบเวลาเกิด (ล้างเวลาเดิมทิ้ง)
    ราศี/ปีนักษัตรถูกคำนวณใหม่จากค่าที่ส่งมาเสมอ"""

    username: str = Field(min_length=2, max_length=50)

    @model_validator(mode="after")
    def hour_and_minute_together(self):
        if (self.birth_hour is None) != (self.birth_minute is None):
            raise ValueError("เวลาเกิดต้องมีทั้งชั่วโมงและนาที")
        return self


class LoginResponse(BaseModel):
    """ผลของ POST /auth/login: otp_required=true = ตรวจรหัสผ่านผ่านแล้วและส่ง OTP ไปทางอีเมลแล้ว
    (ให้เรียก /auth/login/verify ต่อ) ถ้า false = ได้ token ทันที (กรณีปิด LOGIN_OTP_REQUIRED)"""
    otp_required: bool
    message: str | None = None
    expires_in: int | None = None
    resend_in: int | None = None
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserOut | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SocialAuthResponse(BaseModel):
    """ผลของ /auth/google และ /auth/facebook มี 2 กรณี:
    - needs_profile=False: มีบัญชีอยู่แล้ว (หรือจับคู่ด้วยอีเมลได้) → ได้ access_token + user เลย
    - needs_profile=True : ผู้ใช้ใหม่ ยังขาดวันเกิด/ชื่อผู้ใช้ → ได้ registration_token
      (+ email/suggested_username ไว้เติมในฟอร์ม) เอาไปเรียก /auth/social/complete ต่อ"""

    needs_profile: bool
    # True = ผู้ใช้เดิมล็อกอิน social สำเร็จแล้ว แต่ต้องกรอก OTP ที่ส่งไปอีเมล (email) ก่อนถึงจะได้ token
    # → เรียก POST /auth/login/verify ต่อ (ปิดได้ด้วย LOGIN_OTP_REQUIRED=false)
    otp_required: bool = False
    message: str | None = None
    expires_in: int | None = None
    resend_in: int | None = None
    # True = provider (Facebook) ไม่ส่งอีเมลมา ผู้ใช้ต้องกรอกอีเมล + ยืนยัน OTP เองใน /auth/social/complete
    needs_email: bool = False
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserOut | None = None
    registration_token: str | None = None
    email: str | None = None
    suggested_username: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatSource(BaseModel):
    id: str
    title: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


class ChatMessageOut(BaseModel):
    role: str  # "user" หรือ "assistant"
    content: str
    sources: list[ChatSource] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageOut]


# ---------- ประวัติคำทำนาย ----------
from datetime import timezone as _timezone  # noqa: E402

from pydantic import field_serializer  # noqa: E402


class HistoryEntryOut(BaseModel):
    id: int
    kind: str
    category: str
    title: str
    summary: str
    content: str
    is_saved: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _utc_iso(self, v: datetime) -> str:
        # DB เก็บ UTC แบบไม่มี tz — ใส่ tz ให้ชัด ฝั่งแอปจะแปลงเป็นเวลาเครื่องได้ถูกต้อง
        return v.replace(tzinfo=_timezone.utc).isoformat() if v.tzinfo is None else v.isoformat()


class HistoryListOut(BaseModel):
    items: list[HistoryEntryOut]
    total: int


class HistorySavedRequest(BaseModel):
    saved: bool
