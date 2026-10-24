"""
routers/auth.py
----------------
POST /auth/otp/request     — ขอรหัส OTP ทางอีเมล (purpose = signup | reset)
POST /auth/register        — ตรงกับปุ่ม "สมัครสมาชิก" ใน signup_screen.dart (ต้องแนบ otp_code)
POST /auth/login           — ตรงกับปุ่ม "เข้าสู่ระบบ": ตรวจรหัสผ่านแล้วส่ง OTP (ถ้าเปิด LOGIN_OTP_REQUIRED)
POST /auth/login/verify    — กรอก OTP ล็อกอินแล้วได้ token
POST /auth/password/verify-otp — "ลืมรหัสผ่าน?" ขั้น 2: ตรวจ OTP แล้วได้ reset_token
POST /auth/password/reset  — "ลืมรหัสผ่าน?" ขั้น 3: ตั้งรหัสผ่านใหม่ด้วย reset_token
POST /auth/google          — เข้าสู่ระบบ/สมัครด้วย Google (รับ id_token จากแอป)
POST /auth/facebook        — เข้าสู่ระบบ/สมัครด้วย Facebook (รับ access_token จากแอป)
POST /auth/social/complete — ผู้ใช้ social ใหม่กรอกวันเกิด/ชื่อผู้ใช้ให้ครบแล้วสร้างบัญชี
GET  /auth/me              — ตรวจ token คืนข้อมูลผู้ใช้ปัจจุบัน (ใช้เช็คว่า login ค้างอยู่ไหม)
PATCH /auth/me             — แก้ชื่อผู้ใช้/วันเกิด/เวลาเกิด (คำนวณราศีใหม่ให้)
POST /auth/me/avatar       — อัปโหลดรูปโปรไฟล์ (multipart, ฟิลด์ "file")
DELETE /auth/me/avatar     — ลบรูปโปรไฟล์
DELETE /auth/me            — ลบบัญชีและข้อมูลทั้งหมดของผู้ใช้ (ต้องยืนยันด้วยรหัสผ่านหรืออีเมล)
"""

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .. import avatars, crud, login_throttle, mailer, models, otp, security, social
from ..config import settings
from ..database import get_db
from ..schemas import (
    DeleteAccountRequest,
    FacebookLoginRequest,
    GoogleLoginRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
    PasswordResetRequest,
    RegisterRequest,
    ResetTokenResponse,
    SocialAuthResponse,
    SocialCompleteRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer()


@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(data: OtpRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    email = otp.normalize_email(data.email)
    user = crud.get_user_by_email(db, email)

    if data.purpose == otp.PURPOSE_SIGNUP and user:
        raise HTTPException(status_code=400, detail="อีเมลนี้ถูกใช้งานแล้ว")

    # purpose=reset: ตอบสำเร็จเหมือนกันทุกกรณี ไม่ว่าอีเมลนี้มีบัญชีหรือไม่ — กันคน
    # ไล่เดาว่าอีเมลไหนสมัครไว้บ้าง (ส่งจริงเฉพาะเมื่อมีบัญชี)
    if data.purpose == otp.PURPOSE_SIGNUP or user:
        code = otp.issue_otp(db, email, data.purpose)
        # ส่งเป็น background task: SMTP ช้าได้หลายวินาที ไม่ควรให้ผู้ใช้ค้างรอ
        background_tasks.add_task(mailer.send_otp_email, email, code, data.purpose)

    return OtpRequestResponse(
        message="ส่งรหัส OTP ไปที่อีเมลแล้ว (ถ้าไม่พบ ลองดูในโฟลเดอร์สแปม)",
        expires_in=settings.otp_expire_minutes * 60,
        resend_in=settings.otp_resend_cooldown_seconds,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="อีเมลนี้ถูกใช้งานแล้ว")
    if crud.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้นี้ถูกใช้งานแล้ว")

    # เช็คอีเมล/ชื่อผู้ใช้ซ้ำ "ก่อน" ตรวจ OTP โดยตั้งใจ — ถ้าชื่อซ้ำ ผู้ใช้จะได้แก้ชื่อ
    # แล้วส่งใหม่ได้เลยโดย OTP ยังไม่ถูกใช้ไป (ไม่ต้องขอรหัสใหม่)
    otp.verify_otp(db, data.email, otp.PURPOSE_SIGNUP, data.otp_code)

    user = crud.create_user(db, data)
    token = security.create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/password/verify-otp", response_model=ResetTokenResponse)
def verify_reset_otp(data: OtpVerifyRequest, db: Session = Depends(get_db)):
    """ขั้นที่ 2 ของลืมรหัสผ่าน: ตรวจ OTP แล้วแลกเป็น reset_token อายุสั้น เพื่อให้
    ผู้ใช้ไปกรอกรหัสผ่านใหม่ในหน้าถัดไป (OTP ถูกใช้ไปแล้วตรงนี้ ใช้ซ้ำไม่ได้)"""
    otp.verify_otp(db, data.email, otp.PURPOSE_RESET, data.otp_code)
    user = crud.get_user_by_email(db, data.email)
    if not user:
        # OTP ถูกต้องแต่ไม่มีบัญชี — เกิดได้ยากมาก (ออก OTP reset เฉพาะอีเมลที่มีบัญชี)
        raise HTTPException(status_code=400, detail=otp.INVALID_MSG)
    return ResetTokenResponse(reset_token=security.create_reset_token(user.id))


@router.post("/password/reset", response_model=MessageResponse)
def reset_password(data: PasswordResetRequest, db: Session = Depends(get_db)):
    """ขั้นที่ 3: ตั้งรหัสผ่านใหม่ด้วย reset_token ที่ได้จาก /password/verify-otp"""
    user_id = security.decode_reset_token(data.reset_token)
    user = db.get(models.User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="หมดเวลาตั้งรหัสผ่านใหม่ กรุณาขอรหัส OTP อีกครั้ง")
    crud.set_password(db, user, data.new_password)
    return MessageResponse(message="ตั้งรหัสผ่านใหม่เรียบร้อยแล้ว กรุณาเข้าสู่ระบบ")


def _social_login(
    db: Session, identity: social.SocialIdentity, background_tasks: BackgroundTasks
) -> SocialAuthResponse:
    """ลำดับ: จับคู่ด้วย provider id → ไม่เจอก็จับคู่ด้วยอีเมล (ผูกบัญชีเดิม) → ไม่เจอเลย
    = ผู้ใช้ใหม่ ต้องกรอกวันเกิดเพิ่มก่อน"""
    user = crud.get_user_by_provider(db, identity.provider, identity.provider_id)

    if user is None:
        if not identity.email:
            if identity.provider == "facebook":
                # Facebook ไม่ส่งอีเมลให้ (สมัครด้วยเบอร์โทร/ยังไม่ยืนยันอีเมล) → ให้ผู้ใช้กรอก
                # อีเมลเองแล้วยืนยันด้วย OTP ในขั้น /auth/social/complete ไม่ผูกอัตโนมัติ
                # กับบัญชีเดิม จึงไม่มีทางแอบอ้างอีเมลคนอื่น
                return SocialAuthResponse(
                    needs_profile=True,
                    needs_email=True,
                    registration_token=security.create_registration_token(
                        identity.provider, identity.provider_id, "", identity.name
                    ),
                    email=None,
                    suggested_username=(identity.name or "").strip().replace(" ", "")[:50],
                )
            raise HTTPException(
                status_code=400,
                detail="บัญชีนี้ไม่ได้ให้อีเมลมา จึงสมัครด้วยวิธีนี้ไม่ได้ กรุณาใช้อีเมลสมัครแทน",
            )
        if not identity.email_verified:
            raise HTTPException(status_code=400, detail="อีเมลของบัญชีนี้ยังไม่ได้รับการยืนยันกับผู้ให้บริการ")

        user = crud.get_user_by_email(db, identity.email)
        if user is not None:
            # อีเมลเดียวกับบัญชีที่มีอยู่ และ provider ยืนยันแล้วว่าเจ้าของอีเมลคือคนนี้ → ผูกเข้าด้วยกัน
            # (ไม่ทับ id เดิมถ้าบัญชีนั้นผูก provider เดียวกันกับ id อื่นไว้แล้ว)
            existing = user.google_id if identity.provider == "google" else user.facebook_id
            if existing and existing != identity.provider_id:
                raise HTTPException(status_code=409, detail="อีเมลนี้ผูกกับบัญชี social อื่นอยู่แล้ว")
            crud.link_provider(db, user, identity.provider, identity.provider_id)

    if user is not None:
        if settings.login_otp_required:
            # ผู้ใช้เดิมล็อกอินด้วย Google/Facebook ผ่านแล้ว → ยังต้องกรอก OTP ทางอีเมลของบัญชีก่อนได้ token
            email = otp.normalize_email(user.email)
            code = otp.issue_otp(db, email, otp.PURPOSE_LOGIN)
            background_tasks.add_task(mailer.send_otp_email, email, code, otp.PURPOSE_LOGIN)
            return SocialAuthResponse(
                needs_profile=False,
                otp_required=True,
                email=email,
                message="ส่งรหัส OTP ไปที่อีเมลแล้ว (ถ้าไม่พบ ลองดูในโฟลเดอร์สแปม)",
                expires_in=settings.otp_expire_minutes * 60,
                resend_in=settings.otp_resend_cooldown_seconds,
            )
        token = security.create_access_token(user.id)
        return SocialAuthResponse(needs_profile=False, access_token=token, user=UserOut.model_validate(user))

    local = identity.email.split("@")[0]
    suggested = (identity.name or local).strip().replace(" ", "")[:50] or local[:50]
    return SocialAuthResponse(
        needs_profile=True,
        registration_token=security.create_registration_token(
            identity.provider, identity.provider_id, identity.email, identity.name
        ),
        email=identity.email,
        suggested_username=suggested,
    )


@router.post("/google", response_model=SocialAuthResponse)
def login_with_google(data: GoogleLoginRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _social_login(db, social.verify_google_id_token(data.id_token), background_tasks)


@router.post("/facebook", response_model=SocialAuthResponse)
def login_with_facebook(data: FacebookLoginRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _social_login(db, social.verify_facebook_access_token(data.access_token), background_tasks)


@router.post("/social/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def complete_social_signup(data: SocialCompleteRequest, db: Session = Depends(get_db)):
    claims = security.decode_registration_token(data.registration_token)
    if claims is None:
        raise HTTPException(status_code=401, detail="หมดเวลากรอกข้อมูล กรุณาเข้าสู่ระบบด้วย Google/Facebook ใหม่อีกครั้ง")

    provider, provider_id, email = claims["prov"], claims["pid"], claims["email"]
    needs_email = not email  # provider ไม่ส่งอีเมลมา → ใช้อีเมลที่ผู้ใช้กรอก + OTP แทน
    if needs_email:
        if not data.email or not data.otp_code:
            raise HTTPException(status_code=400, detail="กรุณากรอกอีเมลและรหัส OTP")
        email = otp.normalize_email(data.email)

    # กันกรณีส่งซ้ำ/สมัครซ้อนกันระหว่างรอ — ถ้ามีบัญชีแล้วไม่ต้องสร้างใหม่
    if crud.get_user_by_provider(db, provider, provider_id):
        raise HTTPException(status_code=400, detail="บัญชีนี้ถูกสร้างไปแล้ว กรุณาเข้าสู่ระบบ")
    if crud.get_user_by_email(db, email):
        detail = (
            "อีเมลนี้ถูกใช้งานแล้ว กรุณาใช้อีเมลอื่น หรือเข้าสู่ระบบด้วยอีเมลนี้"
            if needs_email
            else "บัญชีนี้ถูกสร้างไปแล้ว กรุณาเข้าสู่ระบบ"
        )
        raise HTTPException(status_code=400, detail=detail)
    if crud.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้นี้ถูกใช้งานแล้ว")

    # ตรวจ OTP หลังเช็คซ้ำทั้งหมด เหมือน /register เพื่อไม่ให้ชื่อซ้ำเผา OTP ทิ้ง
    if needs_email:
        otp.verify_otp(db, email, otp.PURPOSE_SIGNUP, data.otp_code)

    user = crud.create_social_user(
        db, username=data.username, email=email, provider=provider, provider_id=provider_id, birth=data
    )
    token = security.create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    login_throttle.check(data.email, ip)  # ถูกพักอยู่ → 429 ก่อนตรวจรหัสผ่านด้วยซ้ำ
    user = crud.authenticate_user(db, data.email, data.password)
    if not user:
        login_throttle.record_failure(data.email, ip)
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    login_throttle.record_success(data.email)

    if settings.login_otp_required:
        # รหัสผ่านถูกแล้ว → ส่ง OTP ไปที่อีเมล ยังไม่ออก token จนกว่าจะกรอก OTP ถูก
        # (ขอ OTP ซ้ำถี่เกินไปจะโดน 429 จาก cooldown เหมือนขั้นสมัคร)
        email = otp.normalize_email(data.email)
        code = otp.issue_otp(db, email, otp.PURPOSE_LOGIN)
        background_tasks.add_task(mailer.send_otp_email, email, code, otp.PURPOSE_LOGIN)
        return LoginResponse(
            otp_required=True,
            message="ส่งรหัส OTP ไปที่อีเมลแล้ว (ถ้าไม่พบ ลองดูในโฟลเดอร์สแปม)",
            expires_in=settings.otp_expire_minutes * 60,
            resend_in=settings.otp_resend_cooldown_seconds,
        )

    token = security.create_access_token(user.id)
    return LoginResponse(otp_required=False, access_token=token, user=UserOut.model_validate(user))


@router.post("/login/verify", response_model=TokenResponse)
def verify_login_otp(data: OtpVerifyRequest, db: Session = Depends(get_db)):
    """ขั้นที่ 2 ของการล็อกอิน: ตรวจ OTP แล้วออก token (OTP นี้ออกให้เฉพาะหลังรหัสผ่านถูกต้องเท่านั้น)"""
    email = otp.normalize_email(data.email)
    otp.verify_otp(db, email, otp.PURPOSE_LOGIN, data.otp_code)
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    token = security.create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    user_id = security.decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token ไม่ถูกต้องหรือหมดอายุ")
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="ไม่พบผู้ใช้")
    return user


_optional_bearer = HTTPBearer(auto_error=False)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: Session = Depends(get_db),
):
    """ผู้ใช้ที่ login อยู่ หรือ None ถ้าไม่ได้ส่ง token / token ใช้ไม่ได้ (ไม่ error)
    ใช้กับ endpoint สาธารณะที่ "บันทึกประวัติให้" เฉพาะคนที่ login"""
    if credentials is None:
        return None
    user_id = security.decode_access_token(credentials.credentials)
    return db.get(models.User, user_id) if user_id is not None else None


@router.get("/me", response_model=UserOut)
def read_current_user(current_user=Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_current_user(
    data: UpdateProfileRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    other = crud.get_user_by_username(db, data.username)
    if other is not None and other.id != current_user.id:
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้นี้ถูกใช้งานแล้ว")
    return crud.update_profile(db, current_user, data)


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # อ่านเกินเพดานไปนิดเดียวพอ (+1 ไบต์) ไม่โหลดไฟล์ใหญ่ทั้งไฟล์เข้าหน่วยความจำ
    data = await file.read(avatars.MAX_AVATAR_BYTES + 1)
    filename = avatars.save_avatar(current_user.id, data)
    old = current_user.avatar_path
    current_user.avatar_path = filename
    db.commit()
    db.refresh(current_user)
    avatars.delete_avatar_file(old)  # ลบรูปเก่าหลังบันทึกใหม่สำเร็จแล้วเท่านั้น
    return current_user


@router.delete("/me/avatar", response_model=UserOut)
def delete_avatar(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    old = current_user.avatar_path
    current_user.avatar_path = None
    db.commit()
    db.refresh(current_user)
    avatars.delete_avatar_file(old)
    return current_user


@router.delete("/me", response_model=MessageResponse)
def delete_account(
    data: DeleteAccountRequest | None = Body(default=None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ลบบัญชีถาวร: ข้อมูลโปรไฟล์ดวง แชท ประวัติ/รายการที่บันทึก OTP ที่ค้าง และรูปโปรไฟล์
    ย้อนกลับไม่ได้ จึงต้องยืนยันตัวตนอีกครั้ง (กันกรณี token หลุดหรือกดพลาด)"""
    data = data or DeleteAccountRequest()
    if current_user.password_hash:
        if not data.password or not security.verify_password(data.password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="รหัสผ่านไม่ถูกต้อง")
    else:
        if (data.confirm_email or "").strip().lower() != current_user.email.lower():
            raise HTTPException(status_code=400, detail="อีเมลที่พิมพ์ยืนยันไม่ตรงกับบัญชี")

    user_id, email, avatar = current_user.id, current_user.email, current_user.avatar_path
    # ลบตารางที่ผูกกับผู้ใช้ให้ครบเอง ไม่พึ่ง ON DELETE CASCADE ของฐานข้อมูล (SQLite ไม่เปิดไว้)
    db.query(models.HistoryEntry).filter(models.HistoryEntry.user_id == user_id).delete(synchronize_session=False)
    db.query(models.OtpCode).filter(models.OtpCode.email == email).delete(synchronize_session=False)
    db.delete(current_user)  # cascade ไป astro_profile และ chat_messages
    db.commit()
    avatars.delete_avatar_file(avatar)  # ลบไฟล์หลังลบข้อมูลสำเร็จแล้วเท่านั้น
    return MessageResponse(message="ลบบัญชีเรียบร้อยแล้ว")
