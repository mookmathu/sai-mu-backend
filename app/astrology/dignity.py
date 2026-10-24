"""
astrology/dignity.py
----------------------
สถานะ/กำลังดาว (เกษตร อุจจ์ นิจ ประ มหาจักร ฯลฯ).

STATUS: NOT IMPLEMENTED. Spec section 3 explicitly requires this rule table
be built "จากแหล่งอ้างอิงเดียวกัน" (the same reference chosen for the rest of
the engine) — see docs/formulas_needing_review.md, item "dignity.rule_table".
"""

from __future__ import annotations

from .errors import FormulaNotVerifiedError
from .schemas import Dignity, PlanetPosition


def dignities_for(planet: PlanetPosition) -> list[Dignity]:
    raise FormulaNotVerifiedError(
        "dignity.rule_table",
        "เกษตร/อุจจ์/นิจ/ประ/มหาจักร rule table not yet built from a checked source",
    )
