"""
astrology/transit.py
-----------------------
ดาวจรเทียบพื้นดวง (transit snapshots for time-scoped questions).

STATUS: PARTIAL.
  - Sun/Moon transit longitude: reuses ephemeris.py (cited, verified).
  - Everything the legacy app/transit.py adds on top — HOUSE_NAMES topic
    mapping, TOPIC_KEYWORDS_TO_HOUSE, and ASPECT_NAMES — is documented in
    that module's own comments as uncited ("standard Thai house/aspect
    table" with no specific source) and is NOT promoted here as-is. It must
    be re-verified or replaced — see docs/formulas_needing_review.md,
    items "transit.house_topic_mapping" and "relationships.rule_table".
  - Only Sun + Moon are supported; Mars..Ketu transits are blocked on
    ephemeris.py support for those planets.
"""

from __future__ import annotations

from datetime import date, datetime

from .ephemeris import planet_longitude
from .errors import FormulaNotVerifiedError
from .schemas import PlanetId, PlanetPosition, TransitSnapshot

_SUPPORTED = {PlanetId.SURIYA, PlanetId.JANDRA}


def transit_positions(as_of: date, planets: list[PlanetId] | None = None) -> list[PlanetPosition]:
    planets = planets or list(_SUPPORTED)
    unsupported = [p for p in planets if p not in _SUPPORTED]
    if unsupported:
        raise FormulaNotVerifiedError(
            "ephemeris.other_planets",
            f"transit requested for unsupported planets: {[p.value for p in unsupported]}",
        )

    dt = datetime(as_of.year, as_of.month, as_of.day, 12, 0)  # noon snapshot
    out: list[PlanetPosition] = []
    for p in planets:
        longitude, sign = planet_longitude(p, dt)
        out.append(
            PlanetPosition(
                id=p,
                name="อาทิตย์" if p is PlanetId.SURIYA else "จันทร์",
                longitude=longitude,
                sign=sign,
                house=None,  # requires houses.py — not assigned here
            )
        )
    return out


def build_transit_snapshot(as_of: date) -> TransitSnapshot:
    """Positions only — relations_to_natal deliberately left empty until
    astrology.relationships is implemented against a verified source."""
    return TransitSnapshot(as_of=as_of, planets=transit_positions(as_of), relations_to_natal=[])
