from datetime import date

from app import taksa


def test_letters_match_existing_mapping_and_flag_kalakin():
    d = date(2000, 1, 2)  # วันอาทิตย์
    r = taksa.suggest_first_letters(d)
    assert r["day_name"] == "อาทิตย์"
    names = [c["name"] for c in r["categories"]]
    assert names == [c["name"] for c in taksa.TAKSA_CATEGORIES]
    kal = [c for c in r["categories"] if c["avoid"]]
    assert len(kal) == 1 and kal[0]["name"] == "กาลกิณี"
    assert kal[0]["letters"] == list("ศษสหฬฮ")  # วันอาทิตย์ห้าม ศ ษ ส ห ฬ ฮ


def test_every_consonant_appears_once_per_day():
    for day in range(1, 8):  # 7 วันติดกัน
        r = taksa.suggest_first_letters(date(2000, 1, day))
        seen = [ch for c in r["categories"] for ch in c["letters"] if len(ch) == 1 and ch not in "อ"]
        assert len(seen) == len(set(seen))


def _kalakin(d):
    r = taksa.suggest_first_letters(d)
    return "".join(c["letters"][0] if False else "".join(dict.fromkeys(c["letters"])) for c in r["categories"] if c["avoid"])


def test_kalakin_per_day_matches_reference_table():
    # กาลกิณีของแต่ละวัน = กลุ่มประจำวันของ "ดาวก่อนหน้า" ในวงทักษา (อา จ อัง พุธ เสาร์ พฤ ราหู ศุกร์)
    # อาทิตย์-จันทร์-อังคาร-เสาร์ ตรงกับที่บทความตั้งชื่อ (Wongnai) ระบุไว้
    expect = {
        2: "ศษสหฬฮ",  # อาทิตย์
        4: "กขคฆง",  # อังคาร
        5: "จฉชซฌญ",  # พุธ
        6: "ดตถทธน",  # พฤหัสบดี
        7: "ยรลว",  # ศุกร์
        8: "ฎฏฐฑฒณ",  # เสาร์
    }
    for day_of_month, letters in expect.items():
        assert _kalakin(date(2000, 1, day_of_month)) == letters, day_of_month
    assert _kalakin(date(2000, 1, 3)).startswith("อ")  # จันทร์ ห้ามสระ


def test_first_consonant_skips_leading_vowels():
    assert taksa.first_consonant("เกษม") == "ก"
    assert taksa.first_consonant("แพร") == "พ"
    assert taksa.first_consonant("เอก") == "อ"
    assert taksa.first_consonant("ภูมิ") == "ภ"
    fri = date(2000, 1, 7)
    assert taksa.check_name_first_letter("เกษม", fri)["first_letter"] == "ก"
