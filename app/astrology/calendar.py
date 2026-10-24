"""
astrology/calendar.py
----------------------
Calendar helpers shared across the engine (weekday convention, Thai/JS year
conversion). Wraps suriyayart.js_year (cited) and exposes a single
canonical "weekday index" convention (0=อาทิตย์..6=เสาร์) so every module
(taksa, dignity day-rulers, etc.) agrees on it — see taksa.get_thai_day_index
for the previous ad-hoc version this replaces.
"""

from __future__ import annotations

from datetime import date, datetime

from .. import suriyayart

DAY_NAMES_THAI = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"]


def thai_weekday_index(d: date | datetime) -> int:
    """0=อาทิตย์ ... 6=เสาร์. Python's date.weekday() is Mon=0..Sun=6, so we
    shift it. Kept as the single source of truth for this conversion."""
    return (d.weekday() + 1) % 7


def js_year(d: date | datetime) -> int:
    return suriyayart.js_year(d.day, d.month, d.year, 0.5)
