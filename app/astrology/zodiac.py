"""
astrology/zodiac.py
---------------------
Adapts the legacy app.zodiac (Sun-sign only) into the canonical model:
emits a PlanetPosition for the Sun instead of a bare sign string. House
placement is deliberately NOT done here (needs ascendant + house_method —
see astrology.houses).
"""

from __future__ import annotations

from datetime import datetime

from .ephemeris import planet_longitude
from .schemas import PlanetId, PlanetPosition


def sun_position(birth_datetime_local: datetime) -> PlanetPosition:
    longitude, sign = planet_longitude(PlanetId.SURIYA, birth_datetime_local)
    return PlanetPosition(
        id=PlanetId.SURIYA,
        name="อาทิตย์",
        longitude=longitude,
        sign=sign,
        house=None,  # real house assignment needs ascendant/houses.py — never guessed
    )


def moon_position(birth_datetime_local: datetime) -> PlanetPosition:
    longitude, sign = planet_longitude(PlanetId.JANDRA, birth_datetime_local)
    return PlanetPosition(
        id=PlanetId.JANDRA,
        name="จันทร์",
        longitude=longitude,
        sign=sign,
        house=None,  # see houses.py
    )
