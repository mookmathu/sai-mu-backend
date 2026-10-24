"""
rag/schemas.py
----------------
Pydantic models for the RAG layer: Intent Parser output (spec section 8),
Atomic Facts (spec section 9), and the Knowledge Chunk metadata schema
(spec section 10).

These are the contracts that keep Calculation / RAG / LLM strictly
separated: the LLM layer receives only AtomicFact + KnowledgeChunk objects,
never raw NatalChart fields.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Intent Parser (spec section 8)
# ---------------------------------------------------------------------------

class Topic(str, Enum):
    OVERVIEW = "overview"
    PERSONALITY = "personality"
    LOVE = "love"
    CAREER = "career"
    FINANCE = "finance"
    EDUCATION = "education"
    FAMILY = "family"
    CHILDREN = "children"
    SOCIAL = "social"
    FORTUNE = "fortune"
    HEALTH = "health"
    TRAVEL = "travel"
    OBSTACLES = "obstacles"
    FUTURE_OUTLOOK = "future_outlook"
    NAME_CHECK = "name_check"          # existing legacy feature (taksa)
    NUMEROLOGY = "numerology"          # existing legacy feature (phone/plate)


class TimeScopeType(str, Enum):
    NATAL_ONLY = "natal_only"
    POINT_IN_TIME = "point_in_time"
    FUTURE_RANGE = "future_range"
    PAST_RANGE = "past_range"


class TimeScope(BaseModel):
    type: TimeScopeType
    start: Optional[date] = None
    end: Optional[date] = None

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start")
        if v is not None and start is not None and v < start:
            raise ValueError("time_scope.end must be >= time_scope.start")
        return v


class UserContext(BaseModel):
    """Free-form but bounded context the user stated (never inferred facts
    about protected attributes; keep to what's relevant for topic framing)."""

    relationship_status: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Intent(BaseModel):
    """Structured output of app/rag/intent.py. If produced via an LLM call,
    the raw LLM output MUST be validated against this model before use —
    an Intent object is trusted input to query_builder, a raw LLM dict is
    not (spec section 8)."""

    topic: Topic
    subtopic: Optional[str] = None
    time_scope: TimeScope
    requires_natal: bool = True
    requires_transit: bool = False
    requires_taksa: bool = False
    requires_maha_taksa: bool = False
    user_context: UserContext = Field(default_factory=UserContext)


# ---------------------------------------------------------------------------
# Atomic Facts (spec section 9)
# ---------------------------------------------------------------------------

class AtomicFact(BaseModel):
    """One deterministic, calculation-engine-sourced fact. `attributes` is
    intentionally open (dict) because fact_type determines its shape —
    see astrology/facts.py for the fact_types currently emitted."""

    fact_type: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: Literal["calculation_engine"] = "calculation_engine"

    def fact_id(self) -> str:
        """Stable-ish id for citation (supporting_fact_ids in the LLM
        output contract). Not cryptographic — just deterministic per
        fact_type + sorted attribute values."""
        parts = [self.fact_type] + [f"{k}={v}" for k, v in sorted(self.attributes.items())]
        return "|".join(parts)


# ---------------------------------------------------------------------------
# Knowledge Base / chunk schema (spec section 10)
# ---------------------------------------------------------------------------

class ReliabilityTier(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    VALIDATION_ONLY = "validation_only"


class ChunkEntities(BaseModel):
    planet: Optional[str] = None
    house: Optional[int] = None
    sign: Optional[str] = None
    dignity: Optional[str] = None
    taksa_role: Optional[str] = None


class ChunkSource(BaseModel):
    title: str
    author: Optional[str] = None
    edition: Optional[str] = None
    chapter: Optional[str] = None
    page: Optional[str] = None
    url: Optional[str] = None
    rights_note: Optional[str] = Field(
        default=None,
        description="e.g. 'summarized in project's own words; do not ingest "
        "verbatim printed text without a checked copyright/license status'",
    )


class KnowledgeChunk(BaseModel):
    chunk_id: str
    title: str
    content: str
    tradition: str = "thai_astrology"
    category: str = Field(..., description="e.g. 'planet_in_house', 'taksa_role'")
    entities: ChunkEntities = Field(default_factory=ChunkEntities)
    topics: list[Topic] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    source: ChunkSource
    reliability_tier: ReliabilityTier = ReliabilityTier.SECONDARY
