"""
llm/schemas.py
-----------------
Output JSON contract for the LLM synthesis step (spec section 12).
The LLM's raw response MUST be parsed into this model before it is
returned to the API layer or shown to the user — an unvalidated string is
never trusted as "the answer".
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReadingSection(BaseModel):
    title: str
    interpretation: str
    supporting_fact_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ReadingResponse(BaseModel):
    summary: str
    sections: list[ReadingSection] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
