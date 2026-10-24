# เช็กลิสต์ก่อนขึ้นใช้งานจริง (Auth + ค่าตั้ง)

ตั้ง `ENVIRONMENT=production` แล้วสตาร์ท — ถ้ายังมีค่าที่ไม่ปลอดภัย เซิร์ฟเวอร์จะไม่ยอมสตาร์ท
และบอกเป็นข้อๆ ว่าขาดอะไร (ไม่แสดงค่าความลับออกมา) ข้อที่ติ๊กไม่ได้ด้วยโค้ด ต้องทำเองตามด้านล่าง

## 1. ความลับ (ตั้งใน `.env` บนเซิร์ฟเวอร์ ไม่ใส่ในโค้ด/แชท/git)
- [ ] `JWT_SECRET` — สุ่มใหม่ ≥ 32 ตัว: `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] `ADMIN_API_KEY` — สุ่มใหม่ยาวๆ (ใครมีคีย์นี้เข้าหน้าแอดมินได้)
- [ ] `GEMINI_API_KEY` — ถ้าเคยหลุดไปที่ไหน ให้ revoke แล้วสร้างใหม่ใน Google AI Studio
- [ ] `DATABASE_URL` — ใช้ PostgreSQL/Supabase ไม่ใช่ sqlite
- [ ] ไฟล์ `.env` และ `dart_defines.json` ไม่ถูก commit (มี `.gitignore` ให้แล้วทั้งสองโปรเจกต์ — ตรวจด้วย `git status` ก่อน commit ครั้งแรก)

## 2. อีเมล OTP (SMTP)
- [ ] ตั้ง `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` (Gmail: ต้องเปิด 2-Step Verification แล้วสร้าง App Password 16 หลัก)
- [ ] ตั้ง `SMTP_FROM` เช่น `Mutelove <muteloveapp@gmail.com>` (ว่าง = ใช้ SMTP_USER)
- [ ] ลองสมัครด้วยอีเมลจริงหนึ่งครั้ง: OTP ต้องถึงกล่องจดหมาย (ดูโฟลเดอร์สแปมด้วย) ไม่ใช่ขึ้นใน log
- [ ] Gmail ส่งได้วันละจำกัด (บัญชีทั่วไปราว 500 ฉบับ/วัน) ถ้าผู้ใช้เยอะ ให้ย้ายไปบริการส่งอีเมลโดยเฉพาะ

## 3. เข้าสู่ระบบด้วย Google
- [ ] สร้าง OAuth Client ID ชนิด Web ใน Google Cloud Console ใส่ใน `GOOGLE_CLIENT_IDS` (และเป็น `serverClientId` ในแอป)
- [ ] สร้าง Client ID ชนิด Android (ใส่ package name + SHA-1 ของ keystore ที่ใช้ build จริง) และ iOS (bundle id) ให้ตรงกับแอปที่จะปล่อย
- [ ] ถ้า package id ยังเป็นค่าเริ่มต้น (เช่น `com.example.…`) ให้ตัดสินใจเปลี่ยนก่อนสร้าง Client ID — เปลี่ยนทีหลังต้องสร้างใหม่ทั้งหมด
- [ ] OAuth consent screen: ใส่ชื่อแอป อีเมลติดต่อ ลิงก์นโยบายความเป็นส่วนตัว แล้วกด Publish (ถ้ายังเป็น Testing จะใช้ได้เฉพาะ test users)

## 4. เข้าสู่ระบบด้วย Facebook
- [ ] ตั้ง `FACEBOOK_APP_ID` และ `FACEBOOK_APP_SECRET` ใน `.env` ของเซิร์ฟเวอร์เท่านั้น (App Secret ห้ามอยู่ในแอป Flutter)
- [ ] เพิ่ม Android (package + key hash) / iOS (bundle id) ในหน้า Facebook App
- [ ] เปิดสิทธิ์ `email` + `public_profile` และสลับแอปเป็น Live (ต้องมีลิงก์นโยบายความเป็นส่วนตัวและลิงก์คำแนะนำการลบข้อมูล — ในแอปมีเมนู "ลบบัญชี" แล้ว)
- [ ] Facebook อาจต้องผ่านการตรวจแอป (App Review) ก่อนให้คนนอกทีมใช้ ถ้ายังไม่ผ่านจะใช้ได้เฉพาะผู้ทดสอบ/ผู้พัฒนา

## 5. เครือข่ายและการตั้งค่าอื่น
- [ ] ให้บริการผ่าน HTTPS เท่านั้น (ถ้าอยู่หลัง proxy ให้ uvicorn ใช้ `--proxy-headers` เพื่อให้ตัวกันเดารหัสผ่านเห็น IP จริง)
- [ ] `CORS_ORIGINS` ระบุโดเมนเว็บแอปจริง ไม่ใช้ `*`
- [ ] `LOGIN_OTP_REQUIRED=true` (ดีฟอลต์)
- [ ] ตัวกันเดารหัสผ่านและโควตาแชทเก็บในหน่วยความจำ — ถ้ารันหลาย worker/หลายเครื่อง ต่างตัวนับกัน (พอสำหรับโครงงาน)
- [ ] แอปชี้ `baseUrl` ไปที่เซิร์ฟเวอร์จริง (ไม่ใช่ localhost/IP เครื่อง)
