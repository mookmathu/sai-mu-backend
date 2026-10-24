# ตั้งค่า Login ด้วย Google / Facebook + OTP

ลำดับที่แนะนำ: ทำ **ข้อ 1–2 (backend + OTP)** ก่อน ลองสมัครด้วยอีเมลให้ผ่าน แล้วค่อยทำ Google (ข้อ 3) และ Facebook (ข้อ 4) ทีละตัว

---

## 1. Backend

```powershell
pip install -r requirements.txt        # เพิ่ม google-auth, requests
```

**รัน SQL หนึ่งครั้งบน Supabase** (SQL Editor) — ไฟล์ `docs/migrations/2026-10-08_social_login_otp.sql`
(ตาราง `otp_codes` ระบบสร้างเองตอนสตาร์ท แต่ตาราง `users` ที่มีอยู่แล้วต้องแก้เอง: ให้ `password_hash` เป็น NULL ได้ + เพิ่ม `google_id`, `facebook_id`)

แล้วรีสตาร์ท `uvicorn` ใส่ค่าใหม่ใน `.env`:

```env
# --- OTP ทางอีเมล ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx     # App Password ไม่ใช่รหัสผ่าน Gmail ปกติ
# SMTP_FROM=Mutelove <your@gmail.com>  # ไม่ใส่ = ใช้ SMTP_USER

# --- Google (ข้อ 3) ---
GOOGLE_CLIENT_IDS=xxxx.apps.googleusercontent.com

# --- Facebook (ข้อ 4) ---
FACEBOOK_APP_ID=1234567890
FACEBOOK_APP_SECRET=xxxxxxxx           # ห้ามใส่ในแอป Flutter เด็ดขาด
```

## 2. OTP ทางอีเมล

- **ลองก่อนโดยไม่ต้องตั้ง SMTP:** ถ้าไม่ใส่ `SMTP_HOST` ระบบจะ **พิมพ์รหัส OTP ลงหน้าต่าง terminal ของ uvicorn** (บรรทัดที่ขึ้นต้นด้วย `[DEV]`) แทนการส่งอีเมลจริง — ใช้ทดสอบ flow ทั้งหมดได้เลย ก่อนขึ้นใช้งานจริงต้องตั้ง SMTP
- **Gmail App Password:** บัญชี Google → Security → เปิด 2-Step Verification → ค้นหา "App passwords" → สร้างรหัส 16 หลักมาใส่ `SMTP_PASSWORD`
- กฎของ OTP: 6 หลัก หมดอายุ 5 นาที ใช้ได้ครั้งเดียว กรอกผิดได้ 5 ครั้ง ขอใหม่ได้ทุก 60 วินาที (ปรับได้ใน `.env`: `OTP_EXPIRE_MINUTES`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN_SECONDS`)

## 3. Google Sign-In

1. [Google Cloud Console](https://console.cloud.google.com) → สร้าง/เลือกโปรเจกต์ → **APIs & Services → OAuth consent screen** → External → ใส่ชื่อแอป/อีเมล → ที่ **Test users** เพิ่มอีเมล Gmail ที่จะใช้ทดสอบ (สถานะ Testing ใช้ได้เฉพาะคนในรายการนี้)
2. **Credentials → Create credentials → OAuth client ID** สร้าง 2 ตัว:
   - **Web application** → ได้ Client ID → นี่คือ `GOOGLE_CLIENT_IDS` ใน `.env` **และ** `GOOGLE_SERVER_CLIENT_ID` ตอนรัน Flutter
   - **Android** → ใส่ package name (`applicationId` ใน `android/app/build.gradle`) + **SHA-1** ของ keystore ที่ใช้ build
3. หา SHA-1 ของ debug keystore (PowerShell):
   ```powershell
   keytool -list -v -keystore "$env:USERPROFILE\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android
   ```
   (ถ้าปล่อยแอปจริงทีหลัง ต้องเพิ่ม SHA-1 ของ release keystore ด้วย)

## 4. Facebook Login

1. [developers.facebook.com](https://developers.facebook.com) → Create App → ประเภท Consumer/Authenticate → เพิ่มผลิตภัณฑ์ **Facebook Login**
2. **Settings → Basic:** ได้ App ID, App Secret (→ `.env`) และ Client Token (Settings → Advanced)
3. เพิ่มแพลตฟอร์ม **Android:** package name, ชื่อคลาส (`<package>.MainActivity`), และ **Key Hash** ของ debug keystore:
   ```powershell
   keytool -exportcert -alias androiddebugkey -keystore "$env:USERPROFILE\.android\debug.keystore" -storepass android | openssl sha1 -binary | openssl base64
   ```
   (Windows ไม่มี `openssl` ในตัว — ใช้ตัวที่มากับ Git for Windows ได้)
4. **android/app/src/main/res/values/strings.xml** (สร้างถ้ายังไม่มี):
   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <resources>
       <string name="app_name">Mutelove</string>
       <string name="facebook_app_id">1234567890</string>
       <string name="fb_login_protocol_scheme">fb1234567890</string>
       <string name="facebook_client_token">CLIENT_TOKEN</string>
   </resources>
   ```
5. **android/app/src/main/AndroidManifest.xml** — ใส่ใน `<application>`:
   ```xml
   <meta-data android:name="com.facebook.sdk.ApplicationId" android:value="@string/facebook_app_id"/>
   <meta-data android:name="com.facebook.sdk.ClientToken" android:value="@string/facebook_client_token"/>
   <activity android:name="com.facebook.FacebookActivity"
       android:configChanges="keyboard|keyboardHidden|screenLayout|screenSize|orientation"
       android:label="@string/app_name" />
   <activity android:name="com.facebook.CustomTabActivity" android:exported="true">
       <intent-filter>
           <action android:name="android.intent.action.VIEW" />
           <category android:name="android.intent.category.DEFAULT" />
           <category android:name="android.intent.category.BROWSABLE" />
           <data android:scheme="@string/fb_login_protocol_scheme" />
       </intent-filter>
   </activity>
   ```
   (รายละเอียดล่าสุดดูที่ https://facebook.meedu.app — ถ้าเวอร์ชันแพ็กเกจต่างจากนี้ให้ยึดเอกสารนั้น)
6. แอป Facebook อยู่โหมด **Development** โดยค่าเริ่มต้น: เข้าสู่ระบบได้เฉพาะบัญชีที่เป็น Admin/Developer/Tester ของแอป (App roles) — ก่อนให้คนอื่นใช้ต้องสลับเป็น Live

## 5. Flutter

เพิ่มใน `pubspec.yaml` (ใต้ `dependencies:`) แล้วรัน `flutter pub get`:

```yaml
  google_sign_in: ^7.2.0
  flutter_facebook_auth: ^7.2.0
```

รันด้วย:

```powershell
flutter run --dart-define=GOOGLE_SERVER_CLIENT_ID=xxxx.apps.googleusercontent.com --dart-define=API_BASE_URL=http://<ip-เครื่อง>:8000
```

## flow ที่ได้

- **สมัครด้วยอีเมล:** กรอกฟอร์ม → ระบบส่ง OTP ไปอีเมล → กรอก OTP → สร้างบัญชีและเข้าแอป (บัญชีไม่ถูกสร้างจนกว่า OTP จะถูกต้อง)
- **Google / Facebook:** ผู้ใช้เดิมเข้าแอปทันที; ผู้ใช้ใหม่ถูกถามชื่อผู้ใช้ + วันเกิด (ใช้คำนวณราศี) แล้วค่อยสร้างบัญชี ไม่ต้องทำ OTP (provider ยืนยันอีเมลให้แล้ว)
- **อีเมลเดียวกัน:** ถ้าเคยสมัครด้วยอีเมลไว้แล้ว แล้วมา login ด้วย Google/Facebook ที่อีเมลตรงกัน ระบบผูกเป็นบัญชีเดียวกัน
- **ลืมรหัสผ่าน:** กรอกอีเมล → กรอก OTP → ตั้งรหัสผ่านใหม่ → กลับไปหน้า login (บัญชี social ใช้ตั้งรหัสผ่านครั้งแรกได้เช่นกัน)

## ที่ยังไม่ได้ทำ

- iOS (ต้องตั้งค่า `Info.plist` / URL scheme เพิ่ม และ Facebook บน iOS ให้ token แบบ limited ซึ่ง backend ชุดนี้ยังไม่รองรับ) และ Flutter web
- จำกัดจำนวนครั้ง login ผิด (rate limit) ที่ `/auth/login`
