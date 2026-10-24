"""
astrology/ascendant.py
------------------------
Ascendant (ลัคนา) calculation.

STATUS: NOT IMPLEMENTED. No ascendant formula/ayanamsa has been verified
against a primary source yet (needs sidereal reference point + house
system decision — see docs/formulas_needing_review.md, item
"ascendant.formula"). This is the highest-priority open item: houses.py,
and therefore house placement for every planet, depends on it.

Per spec section 19 (Definition of Done) and section 16 (testing):
"Unknown birth time test: ระบบต้องไม่แอบสร้างลัคนาหรือภพที่ต้องพึ่งเวลาเกิด"
— so this function must ALSO refuse (return None / raise) when birth time
is unknown, even after a formula is implemented.
"""

from __future__ import annotations

from datetime import datetime

from .errors import FormulaNotVerifiedError
from .schemas import GeoLocation, PlanetPosition


def calculate_ascendant(
    birth_datetime_local: datetime,
    location: GeoLocation,
    birth_time_known: bool = True,
) -> PlanetPosition | None:
    if not birth_time_known:
        return None
    raise FormulaNotVerifiedError(
        "ascendant.formula",
        "no verified ลัคนา calculation method (ayanamsa + rising-sign formula) "
        "has been chosen yet for this project",
    )
