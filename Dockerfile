FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# ติดตั้ง dependency ก่อน (cache layer เมื่อโค้ดเปลี่ยนแต่ requirements ไม่เปลี่ยน)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# โค้ด + ChromaDB ที่ ingest ไว้แล้ว (app/rag/chroma_db อ่านอย่างเดียวเป็นหลัก)
COPY app ./app
RUN mkdir -p uploads/avatars

# Cloud Run ส่งพอร์ตมาทางตัวแปร PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
