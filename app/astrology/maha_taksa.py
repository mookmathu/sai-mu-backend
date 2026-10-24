"""
astrology/maha_taksa.py
--------------------------
มหาทักษา/ดาวเสวยอายุ.

STATUS: NOT IMPLEMENTED — spec section 3 explicitly gates this feature:
"(หากสูตรได้รับการตรวจสอบจากตำราก่อน implement)". No formula has been
checked yet. See docs/formulas_needing_review.md, item "maha_taksa.formula".
"""

from __future__ import annotations

from datetime import date

from .errors import FormulaNotVerifiedError
from .schemas import MahaTaksaEntry


def build_maha_taksa(birth_date: date, as_of: date) -> list[MahaTaksaEntry]:
    raise FormulaNotVerifiedError(
        "maha_taksa.formula",
        "มหาทักษา/ดาวเสวยอายุ formula not yet verified against a primary "
        "source — explicitly gated by spec section 3",
    )
