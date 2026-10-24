# Mutelove (Sai Mu) — Backend

ระบบหลังบ้านของแอป **Mutelove** (แอปพลิเคชันแนะนำข้อมูลพยากรณ์โชคชะตา โดยใช้
Retrieval-Augmented Generation AI) พัฒนาด้วย **FastAPI** + **PostgreSQL**
ส่วนแชท AI ใช้ **ChromaDB** (ฐานข้อมูลเวกเตอร์) + **Gemini API**

## สิ่งที่ระบบนี้ทำ

- สมัครสมาชิก (ยืนยันอีเมลด้วย OTP) / เข้าสู่ระบบ / ลืมรหัสผ่าน / Google และ Facebook login
- โปรไฟล์ผู้ใช้ (แก้ข้อมูล, รูปโปรไฟล์) — ราศีและปีนักษัตรคำนวณให้อัตโนมัติจากวันเกิด
  ด้วยสูตรสุริยยาตร์ (`app/suriyayart.py`)
- แชทกับ AI (RAG) พร้อมประวัติการสนทนา
- ดวงประจำวัน, สีมงคลประจำวัน, เลขศาสตร์จากชื่อ, เลขเด่นจากตัวเลข (ทะเบียน/เบอร์โทร)
- ประวัติการทำนาย (บันทึก/ลบ)
- สถานที่สิ่งศักดิ์สิทธิ์ (แผนที่) และหน้า Admin สำหรับจัดการเนื้อหา

## โครงสร้างโฟลเดอร์

```
app/
  main.py            จุดเริ่มต้นของ FastAPI
  config.py          ค่าตั้งต้นทั้งหมด (อ่านจาก .env)
  models.py          ตารางฐานข้อมูล (SQLAlchemy)
  schemas.py         รูปแบบข้อมูลเข้า-ออกของ API
  crud.py            ฟังก์ชันอ่าน/เขียนฐานข้อมูล
  security.py        แฮชรหัสผ่าน (bcrypt) และ JWT
  otp.py, mailer.py  ออกและตรวจ OTP, ส่งอีเมล
  suriyayart.py      สูตรคำนวณสุริยยาตร์ (ราศี)
  routers/           endpoint หลัก (auth, chat, daily, history, content, ...)
  api/               endpoint ชุด /api/v1 (ดวงชะตา, ค้นข้อมูลโหราศาสตร์)
  rag/               ระบบ RAG (ingest, retriever, gemini_client, guardrails, eval)
  static/admin/      หน้าเว็บแอดมิน
tests/               ชุดทดสอบอัตโนมัติของ API (pytest)
app/tests/           ชุดทดสอบอื่น (RAG, ดาราศาสตร์, integration)
scripts/             สคริปต์ดูแลข้อมูล
init.sql             schema อ้างอิง (ของจริงสร้างจาก app/models.py)
```

## ตารางหลักในฐานข้อมูล

| ตาราง | เก็บอะไร |
|---|---|
| `users` | บัญชีผู้ใช้ (username, email, รหัสผ่านแฮช, วันเกิด/เวลาเกิด, รูปโปรไฟล์, id Google/Facebook) |
| `user_astro_profiles` | ราศีและปีนักษัตร (ระบบคำนวณให้เอง) |
| `chat_messages` | ข้อความแชท (ผู้ใช้/AI) พร้อมแหล่งอ้างอิง |
| `history_entries` | ประวัติคำทำนายและรายการที่ผู้ใช้บันทึกไว้ |
| `otp_codes` | รหัส OTP (เก็บเฉพาะค่าแฮช) |
| `daily_color_charts` | สีมงคลประจำวัน (เนื้อหาที่ Admin จัดการ) |
| `sacred_places` | สถานที่สิ่งศักดิ์สิทธิ์ (เนื้อหาที่ Admin จัดการ) |

ตารางทั้งหมดถูกสร้างอัตโนมัติตอนเริ่มระบบ (เหมาะกับช่วงพัฒนา — ขึ้นใช้งานจริงแนะนำใช้
Alembic migration แทน)

## สิ่งที่ต้องมีก่อนเริ่ม

- Python 3.11 ขึ้นไป
- Gemini API key (ขอได้ที่ Google AI Studio)
- ฐานข้อมูล PostgreSQL (เช่น Supabase) — ถ้าไม่มี ระบบจะใช้ไฟล์ sqlite
  (`sai_mu_dev.db`) ให้อัตโนมัติ เหมาะกับการลองรันในเครื่อง

## ติดตั้ง

```bash
# 1) ติดตั้งแพ็กเกจ
pip install -r requirements.txt

# 2) สร้างไฟล์ .env ที่โฟลเดอร์นี้ (โฟลเดอร์เดียวกับ requirements.txt)
```

ตัวอย่างไฟล์ `.env`:

```env
# ฐานข้อมูล (ไม่ใส่ = ใช้ sqlite ในเครื่อง)
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME

# ความลับของระบบ — ต้องสุ่มค่าใหม่เองก่อนใช้งานจริง ห้ามใช้ค่า default
JWT_SECRET=ใส่ข้อความสุ่มยาวๆ
ADMIN_API_KEY=ใส่รหัสสำหรับหน้า Admin

# Gemini (จำเป็นสำหรับแชทและการ ingest)
GEMINI_API_KEY=ใส่คีย์ของคุณ

# อีเมล OTP (ไม่ใส่ = โหมดทดสอบ รหัส OTP จะแสดงในหน้าต่าง uvicorn แทนการส่งอีเมล)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=รหัสผ่านแอป 16 หลัก

# Social login (ไม่บังคับ — ดูวิธีตั้งค่าใน SETUP_SOCIAL_LOGIN.md)
GOOGLE_CLIENT_IDS=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
```

> **ความปลอดภัย:** ห้าม commit ไฟล์ `.env` ขึ้น git และห้ามแปะคีย์จริงในแชทหรือ README
> ตรวจว่า `.gitignore` มีบรรทัด `.env` แล้ว

## เตรียมฐานความรู้สำหรับแชท (ทำครั้งแรก)

แชทตอบจากข้อมูลใน ChromaDB จึงต้องสร้างฐานความรู้ก่อนหนึ่งครั้ง รันที่โฟลเดอร์
ที่มี `requirements.txt`:

```bash
python -m app.rag.ingest
```

- ถ้าโดน rate limit (429) กลางทาง รันคำสั่งเดิมซ้ำได้เลย ระบบจะข้ามข้อมูลที่ทำไปแล้ว
- ถ้าแก้ข้อมูลความรู้แล้วต้องการสร้างใหม่ทั้งหมด ใช้ `python -m app.rag.ingest --reset`
- ถ้ายังไม่ได้รันขั้นตอนนี้ `/chat` จะตอบ 503 พร้อมข้อความบอกให้ทำขั้นตอนนี้

## วิธีรัน

### 1) รันบนเครื่องตัวเอง (ลองด้วย Swagger หรือ emulator)

```bash
uvicorn app.main:app --reload
```

เปิด `http://localhost:8000/docs` จะเห็นหน้ารายการ API ที่กดทดลองยิงได้ทันที

### 2) รันให้มือถือจริงเชื่อมได้

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` จำเป็น ไม่เช่นนั้นเครื่องอื่นจะเชื่อมไม่ได้ จากนั้นเลือกวิธีเชื่อม:

**วิธี A: Cloudflare Tunnel (ไม่ต้องอยู่เครือข่ายเดียวกัน)**

เปิดอีกหน้าต่างหนึ่งแล้วรัน

```bash
cloudflared tunnel --url http://localhost:8000
```

จะได้ที่อยู่แบบ `https://xxxx.trycloudflare.com` ให้ใส่เป็น `API_BASE_URL`
ของแอป Flutter (ที่อยู่นี้เปลี่ยนทุกครั้งที่เปิด Tunnel ใหม่) ทดสอบว่าใช้ได้โดยเปิด
`<ที่อยู่>/docs` ในเบราว์เซอร์

**วิธี B: ฮอตสปอตมือถือ / เครือข่ายเดียวกัน**

ให้คอมและมือถืออยู่เครือข่ายเดียวกัน (WiFi มหาวิทยาลัยบางแห่งบล็อกเครื่องไม่ให้คุยกันเอง
ให้ใช้ฮอตสปอตมือถือแทน) ดู IP ของคอมด้วย `ipconfig` แล้วใช้ `http://<IP>:8000`
เป็น `API_BASE_URL` ถ้ามือถือเข้าไม่ได้ ให้เปิดพอร์ตใน Windows Firewall (PowerShell
แบบ Run as administrator):

```powershell
New-NetFirewallRule -DisplayName "Mutelove 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

### 3) รันฝั่งแอป (Flutter)

```bash
cd <โฟลเดอร์แอป Flutter>
flutter run --dart-define-from-file=dart_defines.json
```

ไฟล์ `dart_defines.json` ต้องมี `API_BASE_URL` บรรทัดเดียว เช่น

```json
{
  "API_BASE_URL": "https://xxxx.trycloudflare.com"
}
```

> ต้องรันจากคำสั่งนี้ทุกครั้ง (ไม่ใช่ปุ่ม Run ใน VS Code) และหลังแก้ไฟล์ต้องปิดแอปแล้วรันใหม่
> ไม่ใช่แค่ hot reload

### หน้า Admin

เปิด `http://localhost:8000/admin/` แล้วกรอก Admin Key ให้ตรงกับ `ADMIN_API_KEY` ใน `.env`
ใช้จัดการสีมงคลประจำวันและสถานที่สิ่งศักดิ์สิทธิ์

## Endpoints หลัก

ดูรายละเอียดทั้งหมดและทดลองยิงได้ที่ `/docs`

| กลุ่ม | Path | หน้าที่ |
|---|---|---|
| auth | `POST /auth/otp/request` | ขอรหัส OTP ทางอีเมล |
| auth | `POST /auth/register` | สมัครสมาชิก (ต้องมี OTP) |
| auth | `POST /auth/login` | เข้าสู่ระบบ |
| auth | `POST /auth/google`, `/auth/facebook`, `/auth/social/complete` | เข้าสู่ระบบด้วยบัญชีโซเชียล |
| auth | `POST /auth/password/verify-otp`, `/auth/password/reset` | ลืมรหัสผ่าน |
| auth | `GET/PATCH /auth/me`, `POST/DELETE /auth/me/avatar` | โปรไฟล์และรูปโปรไฟล์ |
| chat | `POST /chat` | ถามแชท AI (RAG) |
| chat | `GET/DELETE /chat/history` | ดู/ล้างประวัติแชท |
| daily | `GET /daily/fortune` | ดวงประจำวัน |
| content | `GET /content/daily-colors`, `/content/daily-colors/today` | สีมงคลประจำวัน |
| content | `GET /content/sacred-places`, `/content/sacred-places/{id}` | สถานที่สิ่งศักดิ์สิทธิ์ |
| numerology | `POST /numerology/name`, `/numerology/number` | เลขศาสตร์จากชื่อ / ตัวเลข |
| history | `GET/PATCH/DELETE /history...` | ประวัติคำทำนายและรายการที่บันทึก |
| admin | `/admin/...` | จัดการเนื้อหา (ต้องมี Admin Key) |

endpoint ที่ต้องล็อกอินให้ส่ง header `Authorization: Bearer <access_token>`
โดย `access_token` (JWT) ได้จาก `/auth/login` หรือ `/auth/register`

## การทดสอบ

```bash
pip install pytest httpx
python -m pytest tests -v
```

ชุดทดสอบอัตโนมัติ 19 กรณี (`tests/test_api.py`) ครอบคลุมการสมัคร/OTP/เข้าสู่ระบบ
โปรไฟล์ แชท ประวัติ เนื้อหาสาธารณะ และสิทธิ์ผู้ดูแล โดยใช้ฐานข้อมูล sqlite ชั่วคราว
และจำลองการเรียก Gemini จึง **ไม่ต้องใช้อินเทอร์เน็ตหรือ API key**
ชุดทดสอบอื่นอยู่ที่ `app/tests/` รันด้วย `python -m pytest app/tests -v`

## ประเมินคุณภาพระบบ RAG

เครื่องมืออยู่ใน `app/rag/eval/` (ดูรายละเอียดใน `app/rag/eval/README.md`)

```bash
# ประเมินการค้นคืนข้อมูล (ไม่เรียก Gemini สร้างคำตอบ) — ได้ค่า Precision/Recall/NDCG และค่า threshold ที่เหมาะสม
python -m app.rag.eval.eval_retrieval --test-set app/rag/eval/test_set_ranking_v3.json --reset

# ประเมินคุณภาพคำตอบ (Hit Rate, MRR, Faithfulness ด้วย LLM-as-a-judge)
python -m app.rag.eval.run_eval --top-k 3
```

- ผลบันทึกไว้ที่ `app/rag/eval/results/`
- `run_eval` ทำต่อจากจุดเดิมได้เมื่อโควตา Gemini หมด (รันคำสั่งเดิมซ้ำ) ใส่ `--reset` เมื่อต้องการเริ่มใหม่
- โมเดลตัวตัดสินตั้งได้ด้วย `JUDGE_MODEL` (ค่าเริ่มต้น `gemini-3.5-flash-lite`)

## ปัญหาที่พบบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| แอปขึ้น "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้" | backend ไม่ได้รัน, `API_BASE_URL` ผิด/เป็นที่อยู่ Tunnel เก่า, หรือไม่ได้ใส่ `--host 0.0.0.0` ทดสอบด้วยการเปิด `<ที่อยู่>/docs` บนมือถือ |
| มือถือเข้าคอมผ่าน IP ไม่ได้ | เครือข่าย (เช่น WiFi มหาวิทยาลัย) บล็อกเครื่องกันเอง ใช้ Cloudflare Tunnel หรือฮอตสปอตมือถือ และเปิดพอร์ต 8000 ใน Firewall |
| `/chat` ตอบ 503 | ยังไม่ได้รัน `python -m app.rag.ingest` หรือ Gemini ไม่ว่าง/โควตาหมด |
| 429 จาก Gemini | โควตาฟรีหมด (รายนาทีรอสักครู่ได้ รายวันต้องรอรีเซ็ต) ตอน ingest/eval รันคำสั่งเดิมซ้ำได้ |
| ไม่ได้รับอีเมล OTP | ถ้าไม่ได้ตั้ง `SMTP_*` รหัสจะแสดงในหน้าต่าง uvicorn แทน |
| `ModuleNotFoundError` | ยังไม่ได้ `pip install -r requirements.txt` |

## ความปลอดภัยก่อนขึ้นใช้งานจริง

- รหัสผ่านแฮชด้วย bcrypt ก่อนเก็บ และ OTP เก็บเฉพาะค่าแฮช
- JWT มีอายุ 7 วัน (ปรับได้ด้วย `JWT_EXPIRE_MINUTES`)
- ต้องตั้ง `JWT_SECRET` และ `ADMIN_API_KEY` เป็นค่าสุ่มของตัวเองเสมอ ห้ามใช้ค่าเริ่มต้นในโค้ด
- ห้าม commit `.env` และ `dart_defines.json` ขึ้น git
- Facebook App Secret ใช้เฉพาะฝั่งเซิร์ฟเวอร์ ห้ามใส่ในแอป Flutter
- รหัส Gmail ที่ใช้ส่ง OTP ให้ใช้ "รหัสผ่านแอป" ไม่ใช่รหัสผ่านบัญชีจริง