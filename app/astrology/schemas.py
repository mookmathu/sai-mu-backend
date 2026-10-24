"""
astrology/schemas.py
---------------------
Canonical Astrology Data Model — Pydantic port of spec section 5.

This is the ONLY shape a natal chart / transit snapshot is allowed to take
once it leaves the Calculation Engine. RAG and LLM layers read this model;
they never re-derive astrology facts themselves.

Every rule-table-driven field (dignities, taksa, maha_taksa, relationships)
carries a `source_reference` on the object that produced it (see
SourceReference below) so a reading can always be traced back to a text.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared enums — kept intentionally small for V1 scope (spec section 3).
# Extend only when a new value is backed by a checked source_reference.
# ---------------------------------------------------------------------------

class ThaiZodiacSign(str, Enum):
    MESHA = "เมษ"
    VRISHABHA = "พฤษภ"
    MITHUNA = "เมถุน"
    KARKATA = "กรกฎ"
    SIMHA = "สิงห์"
    KANYA = "กันย์"
    TULA = "ตุลย์"
    VRISHCHIKA = "พิจิก"
    DHANU = "ธนู"
    MAKARA = "มังกร"
    KUMBHA = "กุมภ์"
    MINA = "มีน"


class PlanetId(str, Enum):
    """1-9 classical grahas used in Thai astrology (สุริยะ..เกตุ).
    Longitudes/positions for anything beyond Sun (1) and Moon (2) are NOT
    implemented yet — see docs/formulas_needing_review.md."""
    SURIYA = "suriya"      # อาทิตย์ (Sun) — implemented (suriyayart.py)
    JANDRA = "jandra"      # จันทร์ (Moon) — implemented (suriyayart.py)
    ANGKARN = "angkarn"    # อังคาร (Mars) — NOT implemented
    PUTH = "puth"          # พุธ (Mercury) — NOT implemented
    PRUHASBODI = "pruhasbodi"  # พฤหัสบดี (Jupiter) — NOT implemented
    SUK = "suk"            # ศุกร์ (Venus) — NOT implemented
    SAO = "sao"            # เสาร์ (Saturn) — NOT implemented
    RAHU = "rahu"          # ราหู — NOT implemented
    KETU = "ketu"          # เกตุ — NOT implemented


class TaksaRole(str, Enum):
    """8 ภูมิแห่งทักษา (spec section 3)."""
    BORIWAN = "บริวาร"
    AYU = "อายุ"
    DET = "เดช"
    SI = "ศรี"
    MOONLA = "มูละ"
    UTSAHA = "อุตสาหะ"
    MONTRI = "มนตรี"
    KALAKINI = "กาลกิณี"


class TimeScopeType(str, Enum):
    NATAL_ONLY = "natal_only"
    POINT_IN_TIME = "point_in_time"
    FUTURE_RANGE = "future_range"
    PAST_RANGE = "past_range"


class ReliabilityTier(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    VALIDATION_ONLY = "validation_only"


class WarningLevel(str, Enum):
    INFO = "info"
    LIMITATION = "limitation"   # e.g. unknown birth time -> no ascendant
    ERROR = "error"


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class SourceReference(BaseModel):
    """Traceable citation for a rule-table entry or computed value.
    Required on every dignity/taksa/maha_taksa/relationship entry per spec
    section 18, item 4 ("ทุก rule table ต้องมี source_reference field")."""

    title: str
    author: Optional[str] = None
    edition: Optional[str] = None
    chapter: Optional[str] = None
    page: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None


class GeoLocation(BaseModel):
    lat: float
    lon: float
    timezone: Optional[str] = Field(
        default=None, description="IANA tz name, e.g. 'Asia/Bangkok'"
    )
    place_name: Optional[str] = None


class SystemInfo(BaseModel):
    """Which calculation tradition/method produced this chart — required
    on every chart so results are reproducible (spec section 18, item 1
    and section 15: 'เก็บ calculation_method/version ใน chart ทุกครั้ง')."""

    tradition: str = "thai_astrology"
    calculation_method: str = Field(
        ..., description="e.g. 'suriyayart' — must be an explicit, chosen value"
    )
    ayanamsa_or_reference: str = Field(
        ..., description="explicit sidereal reference used; no silent default"
    )
    house_method: str = Field(
        ..., description="explicit house-division method used"
    )
    version: str = "1.0"


class Dignity(BaseModel):
    """สถานะ/กำลังดาว เช่น เกษตร อุจจ์ นิจ ประ มหาจักร ฯลฯ (spec section 3)."""

    name: str = Field(..., description="e.g. 'เกษตร', 'อุจจ์', 'นิจ'")
    strength_modifier: Optional[float] = None
    source_reference: SourceReference


class PlanetPosition(BaseModel):
    id: PlanetId
    name: str
    longitude: float
    sign: ThaiZodiacSign
    house: Optional[int] = Field(
        default=None, ge=1, le=12,
        description="None when house_method/ascendant is not yet available — "
        "never a placeholder value. See astrology/houses.py.",
    )
    dignities: list[Dignity] = Field(default_factory=list)
    retrograde: Optional[bool] = None


class House(BaseModel):
    house: int = Field(..., ge=1, le=12)
    thai_name: str = Field(..., description="e.g. 'ตนุ', 'กดุมภะ' ...")
    sign: ThaiZodiacSign
    lord: PlanetId


class PlanetRelationship(BaseModel):
    """ความสัมพันธ์ดาวตามนิยามโหราศาสตร์ไทยที่เลือกใช้ (spec section 3) —
    NOT the same as Western aspects; must not be auto-derived from Western
    aspect angles unless explicitly instructed."""

    planet_a: PlanetId
    planet_b: PlanetId
    relation: str = Field(..., description="e.g. 'เล็ง', 'ตรีโกณ' per chosen tradition")
    source_reference: SourceReference


class TaksaEntry(BaseModel):
    role: TaksaRole
    ruling_planet: PlanetId
    source_reference: SourceReference


class TaksaChart(BaseModel):
    """ทักษา 8 ภูมิ, keyed by birth weekday. Day/night (Rahu) distinction
    is a known current gap — see docs/formulas_needing_review.md."""

    birth_weekday: str
    day_night: Optional[str] = Field(
        default=None, description="'day' | 'night' — needed for Rahu placement; "
        "None means not yet distinguished (known limitation)"
    )
    entries: list[TaksaEntry] = Field(default_factory=list)


class MahaTaksaEntry(BaseModel):
    """มหาทักษา/ดาวเสวยอายุ — spec explicitly gates this: 'หากสูตรได้รับการ
    ตรวจสอบจากตำราก่อน implement'. Do not populate without a checked source."""

    period_label: str
    ruling_planet: PlanetId
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    source_reference: SourceReference


class NatalData(BaseModel):
    birth_datetime_local: datetime
    location: GeoLocation
    ascendant: Optional[PlanetPosition] = Field(
        default=None,
        description="None when birth time is unknown/unreliable — never guessed",
    )
    planets: list[PlanetPosition] = Field(default_factory=list)
    houses: list[House] = Field(default_factory=list)
    relationships: list[PlanetRelationship] = Field(default_factory=list)
    taksa: Optional[TaksaChart] = None
    maha_taksa: list[MahaTaksaEntry] = Field(default_factory=list)


class TransitSnapshot(BaseModel):
    as_of: date
    planets: list[PlanetPosition] = Field(default_factory=list)
    relations_to_natal: list[PlanetRelationship] = Field(default_factory=list)


class CalculationWarning(BaseModel):
    level: WarningLevel
    code: str = Field(..., description="e.g. 'unknown_birth_time', 'unsupported_planet'")
    message: str


class NatalChart(BaseModel):
    """Top-level object — the only artifact the Calculation Engine hands to
    RAG/LLM layers."""

    chart_id: UUID = Field(default_factory=uuid4)
    system: SystemInfo
    native: NatalData
    transits: list[TransitSnapshot] = Field(default_factory=list)
    calculation_warnings: list[CalculationWarning] = Field(default_factory=list)

    model_config = {"json_schema_extra": {"title": "CanonicalNatalChart"}}
