"""
astrology/houses.py
---------------------
12-house (ภพ) assignment and house-lord table.

STATUS: NOT IMPLEMENTED. Depends on ascendant.py (not yet verified) and on
an explicit house_method (e.g. whole-sign vs. equal-house) that has not
been chosen. Thai-name-per-house table (ตนุ, กดุมภะ, ...) also needs a
primary-source check before being hardcoded — see
docs/formulas_needing_review.md, item "houses.method_and_names".
"""

from __future__ import annotations

from .errors import FormulaNotVerifiedError
from .schemas import House, PlanetPosition, SystemInfo


def assign_house(planet_longitude_deg: float, ascendant_longitude_deg: float) -> int:
    raise FormulaNotVerifiedError(
        "houses.method_and_names",
        "house_method not yet chosen/verified (whole-sign vs equal-house vs other)",
    )


def build_house_table(ascendant: PlanetPosition, system: SystemInfo) -> list[House]:
    raise FormulaNotVerifiedError(
        "houses.method_and_names",
        "Thai house-name table (ตนุ, กดุมภะ, ...) and lord assignment not yet sourced",
    )
