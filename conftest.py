"""ตั้งค่า env สำหรับทดสอบก่อนที่ pytest จะ import app (ทำให้รัน `pytest` เฉยๆ ที่รากโปรเจกต์ได้ทั้งชุด)

settings อ่านค่าตอน import ครั้งแรก ถ้า app/tests ถูก import ก่อน tests/conftest.py ค่าจะมาจาก .env จริง
ไฟล์นี้อยู่ที่ราก จึงถูกโหลดก่อนเสมอ และไม่แตะฐานข้อมูลจริง
"""
import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
