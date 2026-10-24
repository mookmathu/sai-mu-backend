from app.rag.gemini_client import SYSTEM_PROMPT, strip_particles


def test_strip_particles_removes_endings_only():
    assert strip_particles("เบอร์นี้ดีนะคะ ลองดูค่ะ 😊") == "เบอร์นี้ดี ลองดู 😊"
    assert strip_particles("ได้เลยครับ!") == "ได้เลย!"
    assert strip_particles("ใช่ไหมคะ?") == "ใช่ไหม?"


def test_strip_particles_keeps_words_that_start_with_same_letters():
    assert strip_particles("คะแนนสูงมาก") == "คะแนนสูงมาก"
    assert strip_particles("เขาชนะ ไปเลย") == "เขาชนะ ไปเลย"  # "ชนะ" เป็นคำจริง ไม่ใช่คำลงท้าย
    assert strip_particles("วันนี้ดีนะ ไปเลย") == "วันนี้ดี ไปเลย"  # "นะ" ท้ายประโยคถูกตัด (ตาม prompt)


def test_system_prompt_forbids_particles():
    assert "ห้ามใช้คำลงท้าย" in SYSTEM_PROMPT
