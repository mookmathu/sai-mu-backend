"""
Spec section 16: "Unknown birth time test: ระบบต้องไม่แอบสร้างลัคนาหรือภพที่
ต้องพึ่งเวลาเกิด" — this must hold both before and after ascendant.py gets a
real formula, so it's asserted independently of FormulaNotVerifiedError.
"""

from datetime import datetime

from app.astrology.ascendant import calculate_ascendant
from app.astrology.schemas import GeoLocation


def test_unknown_birth_time_never_produces_ascendant():
    result = calculate_ascendant(
        birth_datetime_local=datetime(2004, 10, 15, 14, 35),
        location=GeoLocation(lat=13.7563, lon=100.5018),
        birth_time_known=False,
    )
    assert result is None
