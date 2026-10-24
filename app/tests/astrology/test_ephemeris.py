"""
Golden test per spec section 16: cross-checks ephemeris.planet_longitude
against the exact sample values baked into the original suriyatr1.xls
spreadsheet (see suriyayart.py's own __main__ block for the same case).
Day=16, Month=12, Year=2001, Time=11:11 -> Sun rasi index 8, Moon rasi index 8.
"""

from datetime import datetime

import pytest

from app.astrology.ephemeris import RASI_ORDER, planet_longitude
from app.astrology.errors import FormulaNotVerifiedError
from app.astrology.schemas import PlanetId, ThaiZodiacSign


def test_sun_rasi_matches_golden_case():
    dt = datetime(2001, 12, 16, 11, 11)
    _, sign = planet_longitude(PlanetId.SURIYA, dt)
    assert sign == RASI_ORDER[8] == ThaiZodiacSign.DHANU


def test_moon_rasi_matches_golden_case():
    dt = datetime(2001, 12, 16, 11, 11)
    _, sign = planet_longitude(PlanetId.JANDRA, dt)
    assert sign == RASI_ORDER[8] == ThaiZodiacSign.DHANU


def test_unsupported_planet_raises_not_guesses():
    dt = datetime(2001, 12, 16, 11, 11)
    with pytest.raises(FormulaNotVerifiedError):
        planet_longitude(PlanetId.ANGKARN, dt)
