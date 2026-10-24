"""
astrology/taksa.py
---------------------
ทักษา 8 ภูมิ — wraps the legacy app.taksa rotation logic (correct rotation
mechanics, reused as-is) and emits it in the canonical TaksaChart shape.

IMPORTANT CAVEAT (carried over from app/taksa.py's own docstring): the
category rotation used here is documented as "general Thai astrology
knowledge, not tied to one specific source" — it is NOT yet backed by a
checked primary-source reference. It is marked reliability="secondary" /
source note "unverified" below. Per spec section 18 item 4, this must be
replaced with a proper SourceReference before this module is treated as
production-ready — see docs/formulas_needing_review.md, item "taksa.source".

KNOWN GAP: does not yet distinguish พุธกลางวัน / พุธกลางคืน (Rahu) — the
legacy code documents this explicitly. `day_night` is left None until that
is implemented (see docs/formulas_needing_review.md, item "taksa.day_night").
"""

from __future__ import annotations

from datetime import date

from .. import taksa as _legacy_taksa
from .schemas import PlanetId, SourceReference, TaksaChart, TaksaEntry, TaksaRole

_UNVERIFIED_SOURCE = SourceReference(
    title="ความรู้ทั่วไปทางโหราศาสตร์ไทย (ทักษาปกรณ์)",
    note=(
        "UNVERIFIED: legacy implementation notes this is general knowledge, "
        "not tied to one specific ตำรา. Needs a checked primary source "
        "before production use — see docs/formulas_needing_review.md."
    ),
)

# Legacy category order matches TaksaRole enum order 0..7.
_ROLE_ORDER = [
    TaksaRole.BORIWAN,
    TaksaRole.AYU,
    TaksaRole.DET,
    TaksaRole.SI,
    TaksaRole.MOONLA,
    TaksaRole.UTSAHA,
    TaksaRole.MONTRI,
    TaksaRole.KALAKINI,
]

# NOTE: legacy taksa.py does not assign a *ruling planet* per category, only
# a consonant group — that planet<->category mapping is itself an unverified
# piece (see docs/formulas_needing_review.md, item "taksa.ruling_planets").
# Left as None/omitted until sourced; PlanetId is required by the schema, so
# for now we do not fabricate a value and instead raise if this is called.
def build_taksa_chart(birth_date: date) -> TaksaChart:
    from .errors import FormulaNotVerifiedError

    raise FormulaNotVerifiedError(
        "taksa.ruling_planets",
        "consonant-group-per-day rotation is implemented (app/taksa.py) but "
        "the ruling-planet-per-role mapping required by the canonical "
        "TaksaChart schema has not been sourced yet",
    )


def consonant_groups_for_day(birth_date: date) -> dict[str, list[str]]:
    """Passthrough to the working legacy rotation (day_index -> consonant
    groups per role). Safe to use for the existing name-checking feature;
    NOT sufficient on its own for the canonical TaksaChart (see above)."""
    day_index = _legacy_taksa.get_thai_day_index(birth_date)
    return _legacy_taksa.get_taksa_mapping(day_index)
