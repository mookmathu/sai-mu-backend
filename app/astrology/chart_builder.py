"""
astrology/chart_builder.py
-----------------------------
Assembles the ONLY parts of the canonical NatalChart that currently have a
verified calculation (Sun + Moon sign, via ephemeris.py) into a real
NatalChart object, and records every missing piece as a
CalculationWarning instead of silently omitting it — so API/LLM callers
can see exactly what a chart does and doesn't cover yet
(spec section 19: "กรณีไม่ทราบเวลาเกิด ระบบแจ้งข้อจำกัดและไม่แสดงข้อมูลที่คำนวณไม่ได้").
"""

from __future__ import annotations

from datetime import date, datetime, time

from .ascendant import calculate_ascendant
from .errors import FormulaNotVerifiedError
from .schemas import (
    CalculationWarning,
    GeoLocation,
    NatalChart,
    NatalData,
    SystemInfo,
    WarningLevel,
)
from .zodiac import moon_position, sun_position

# Thai astrology's Suriyayart method is calendar-based, not observational —
# it does not require lat/lon. We still carry a GeoLocation on the chart
# (per canonical model) but until ascendant/houses need real geography, an
# unset location is recorded as a limitation rather than guessed.
_DEFAULT_LOCATION_NOTE = (
    "ไม่มีการเก็บพิกัดสถานที่เกิดของผู้ใช้ในระบบปัจจุบัน (ยังไม่จำเป็นสำหรับ "
    "สูตรสุริยยาตร์ที่ใช้อยู่ตอนนี้ ซึ่งเป็นการคำนวณจากปฏิทิน ไม่ใช่ตำแหน่งภูมิศาสตร์) "
    "แต่จะจำเป็นทันทีที่เริ่มคำนวณลัคนา"
)


def build_natal_chart(
    birth_date: date,
    birth_time: time | None,
    location: GeoLocation | None = None,
) -> NatalChart:
    warnings: list[CalculationWarning] = []

    birth_time_known = birth_time is not None
    effective_time = birth_time or time(12, 0)  # noon fallback, matches legacy zodiac.py behaviour
    if not birth_time_known:
        warnings.append(
            CalculationWarning(
                level=WarningLevel.LIMITATION,
                code="unknown_birth_time",
                message=(
                    "ไม่ทราบเวลาเกิด — ใช้เที่ยงวันแทนสำหรับคำนวณราศีอาทิตย์/จันทร์เท่านั้น "
                    "ลัคนาและภพจะไม่ถูกคำนวณ (เป็น None) จนกว่าจะทราบเวลาเกิดจริง"
                ),
            )
        )

    birth_datetime_local = datetime.combine(birth_date, effective_time)
    location = location or GeoLocation(lat=13.7563, lon=100.5018, timezone="Asia/Bangkok")
    if location.place_name is None:
        warnings.append(
            CalculationWarning(level=WarningLevel.INFO, code="no_location_collected", message=_DEFAULT_LOCATION_NOTE)
        )

    planets = [sun_position(birth_datetime_local), moon_position(birth_datetime_local)]

    try:
        ascendant = calculate_ascendant(birth_datetime_local, location, birth_time_known=birth_time_known)
    except FormulaNotVerifiedError:
        # Expected today for every user, not a server error — see
        # docs/formulas_needing_review.md item 1. Surface it as a
        # calculation_warning instead of a 500.
        ascendant = None
    if ascendant is None:
        warnings.append(
            CalculationWarning(
                level=WarningLevel.LIMITATION,
                code="ascendant_not_available",
                message="ยังไม่มีสูตรลัคนาที่ตรวจสอบแล้ว (ดู docs/formulas_needing_review.md ข้อ 1) — "
                "ภพ (houses) และดาวเจ้าเรือนจึงยังไม่ถูกคำนวณด้วยเหตุผลเดียวกัน",
            )
        )

    warnings.append(
        CalculationWarning(
            level=WarningLevel.LIMITATION,
            code="unsupported_planets",
            message="ยังไม่รองรับอังคาร พุธ พฤหัสบดี ศุกร์ เสาร์ ราหู เกตุ (มีเฉพาะอาทิตย์/จันทร์)",
        )
    )

    native = NatalData(
        birth_datetime_local=birth_datetime_local,
        location=location,
        ascendant=ascendant,
        planets=planets,
        houses=[],
        relationships=[],
        taksa=None,
        maha_taksa=[],
    )

    system = SystemInfo(
        calculation_method="suriyayart",
        ayanamsa_or_reference="not_applicable_calendar_based_method",
        house_method="not_implemented",
        version="1.0",
    )

    return NatalChart(system=system, native=native, transits=[], calculation_warnings=warnings)
