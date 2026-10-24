"""
astrology/ephemeris.py
-----------------------
Planetary-longitude layer of the Calculation Engine.

STATUS:
  - Sun (suriya) / Moon (jandra): IMPLEMENTED, wraps app.suriyayart which is
    a cited, cell-by-cell port of the classical Suriyayart (สุริยยาตร์)
    method (source: พระคัมภีร์สุริยยาตรศิวาคม, transliterated from
    suriyatr1.xls by อาจารย์สมเกียรติ ฟุ้งเกียรติ). See suriyayart.py header.
  - All other planets (Mars..Ketu): NOT IMPLEMENTED. No ephemeris method has
    been chosen/verified yet (see docs/formulas_needing_review.md, item
    "ephemeris.other_planets"). Calling `planet_longitude` for them raises
    FormulaNotVerifiedError rather than approximating.
"""

from __future__ import annotations

from datetime import datetime

from .. import suriyayart
from .errors import FormulaNotVerifiedError
from .schemas import PlanetId, PlanetPosition, ThaiZodiacSign

RASI_ORDER: list[ThaiZodiacSign] = [
    ThaiZodiacSign.MESHA,
    ThaiZodiacSign.VRISHABHA,
    ThaiZodiacSign.MITHUNA,
    ThaiZodiacSign.KARKATA,
    ThaiZodiacSign.SIMHA,
    ThaiZodiacSign.KANYA,
    ThaiZodiacSign.TULA,
    ThaiZodiacSign.VRISHCHIKA,
    ThaiZodiacSign.DHANU,
    ThaiZodiacSign.MAKARA,
    ThaiZodiacSign.KUMBHA,
    ThaiZodiacSign.MINA,
]

_SUPPORTED_PLANETS = {PlanetId.SURIYA, PlanetId.JANDRA}


def _time_frac(dt: datetime) -> float:
    return (dt.hour + dt.minute / 60 + dt.second / 3600) / 24


def planet_longitude(planet: PlanetId, birth_datetime_local: datetime) -> tuple[float, ThaiZodiacSign]:
    """Returns (absolute longitude in degrees, sign). House is NOT assigned
    here — see astrology.houses for house placement, which additionally
    needs the ascendant/house_method."""
    if planet not in _SUPPORTED_PLANETS:
        raise FormulaNotVerifiedError(
            "ephemeris.other_planets",
            f"no verified calculation method chosen for planet={planet.value}",
        )

    day, month, year = birth_datetime_local.day, birth_datetime_local.month, birth_datetime_local.year
    tf = _time_frac(birth_datetime_local)

    if planet is PlanetId.SURIYA:
        rasi_idx, degree, libda = suriyayart.sun_rasi(day, month, year, tf)
    else:  # PlanetId.JANDRA
        rasi_idx, degree, libda = suriyayart.moon_rasi(day, month, year, tf)

    longitude = rasi_idx * 30 + degree + libda / 60
    return longitude, RASI_ORDER[rasi_idx]
