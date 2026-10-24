"""
config.py
---------
อ่านค่า config จาก environment variable / ไฟล์ .env
ห้ามฮาร์ดโค้ดรหัสผ่าน DB หรือ JWT secret ไว้ในโค้ดเด็ดขาด
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ตัวอย่าง: postgresql+psycopg2://user:password@localhost:5432/sai_mu_db
    # ถ้าไม่ตั้งค่า จะ fallback เป็น sqlite ไฟล์เดียวสำหรับรันทดสอบในเครื่องได้ทันที
    database_url: str = "sqlite:///./sai_mu_dev.db"

    # "development" (ดีฟอลต์) หรือ "production" — production จะตรวจค่าตั้งตอนสตาร์ทเข้มขึ้น
    # และไม่ยอมเริ่มทำงานถ้ายังใช้ค่า default ที่ไม่ปลอดภัย (ดู app/startup_checks.py)
    environment: str = "development"
    # โดเมนที่อนุญาตให้เรียก API จากเว็บ คั่นด้วย , ("*" = ทุกที่ ใช้ตอน dev เท่านั้น)
    cors_origins: str = "*"

    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # โทเค็นอยู่ได้ 7 วัน

    # กุญแจสำหรับหน้าเว็บแอดมิน (admin/index.html) ใช้จัดการเนื้อหา (เสื้อสีมงคล/
    # สถานที่สิ่งศักดิ์สิทธิ์) — ง่ายกว่าทำระบบ role/permission เต็มรูปแบบ เพราะ
    # มีแค่เจ้าของแอปคนเดียวที่ต้องเข้าถึงตอนนี้ ตั้งค่าจริงผ่าน .env เสมอ
    # ห้ามใช้ค่า default นี้ตอน deploy จริงเด็ดขาด
    admin_api_key: str = "CHANGE_ME_ADMIN_KEY"

    # --- OTP ทางอีเมล (สมัครสมาชิก / ลืมรหัสผ่าน) ---
    # ถ้า smtp_host ว่าง = โหมด dev: ไม่ส่งอีเมลจริง แต่พิมพ์รหัส OTP ลง log ของ
    # เซิร์ฟเวอร์แทน (uvicorn console) จะได้ลองระบบได้ทันทีโดยไม่ต้องตั้งค่า SMTP
    # ตัวอย่าง Gmail: SMTP_HOST=smtp.gmail.com SMTP_PORT=587 SMTP_USER=you@gmail.com
    # SMTP_PASSWORD=<App Password 16 หลัก ไม่ใช่รหัสผ่านปกติ — ต้องเปิด 2-Step ก่อน>
    smtp_host: str = ""
    smtp_port: int = 587  # 587 = STARTTLS, 465 = SSL
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # ว่าง = ใช้ smtp_user
    # ส่งอีเมลผ่าน Brevo HTTPS API (ใช้เมื่อโฮสต์บล็อกพอร์ต SMTP เช่น Render แผน Free)
    # ถ้าตั้ง brevo_api_key จะใช้ทางนี้ก่อน SMTP — brevo_sender คืออีเมลที่ยืนยันไว้ใน Brevo (ว่าง = ใช้ smtp_user)
    brevo_api_key: str = ""
    brevo_sender: str = ""
    otp_expire_minutes: int = 5
    otp_max_attempts: int = 5  # กรอกผิดเกินนี้ = รหัสนั้นใช้ไม่ได้แล้ว ต้องขอใหม่
    otp_resend_cooldown_seconds: int = 60
    # ล็อกอินด้วยอีเมลต้องกรอก OTP ทุกครั้ง (ตั้ง LOGIN_OTP_REQUIRED=false ใน .env เพื่อปิดตอนพัฒนา)
    login_otp_required: bool = True

    # --- Social login ---
    # Google: Client ID ของ "Web application" (ตัวเดียวกับที่ใส่เป็น serverClientId
    # ในแอป Flutter) — คั่นด้วย , ได้ถ้ามีหลายตัว backend จะตรวจว่า id_token ที่ได้มา
    # ถูกออกให้แอปเราจริง ไม่ใช่ token ของแอปอื่น
    google_client_ids: str = ""
    # Facebook: App ID + App Secret จาก developers.facebook.com (ใช้ตรวจ token ฝั่ง
    # เซิร์ฟเวอร์ผ่าน Graph API /debug_token — ห้ามใส่ App Secret ในแอป Flutter เด็ดขาด)
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    # อายุ token ชั่วคราวระหว่างที่ผู้ใช้ social ใหม่กรอกวันเกิด/ชื่อผู้ใช้ให้ครบ
    registration_token_expire_minutes: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def google_client_id_list(self) -> list[str]:
        return [c.strip() for c in self.google_client_ids.split(",") if c.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
