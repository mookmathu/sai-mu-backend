"""
astrology/relationships.py
-----------------------------
ความสัมพันธ์ดาวตามนิยามโหราศาสตร์ไทยที่เลือกใช้ (เช่น เล็ง ตรีโกณ ฯลฯ),
explicitly NOT Western aspects (spec section 3: "โดยไม่ปน Western aspect
โดยอัตโนมัติ").

STATUS: NOT IMPLEMENTED — no relationship rule table has been sourced yet.
The legacy app.transit.ASPECT_NAMES table is a 7-step aspect list that its
own docstring calls "standard Thai aspect table" WITHOUT a specific citation,
so it must be re-verified (or replaced) before being promoted here — see
docs/formulas_needing_review.md, item "relationships.rule_table".
"""

from __future__ import annotations

from .errors import FormulaNotVerifiedError
from .schemas import PlanetPosition, PlanetRelationship


def relationships_between(planets: list[PlanetPosition]) -> list[PlanetRelationship]:
    raise FormulaNotVerifiedError(
        "relationships.rule_table",
        "Thai planet-relationship rule table (เล็ง/ตรีโกณ/ฯลฯ) not yet "
        "verified against a primary source; legacy ASPECT_NAMES in "
        "transit.py is uncited and must not be reused as-is",
    )
