"""
llm/interpreter.py
---------------------
Calls the LLM with the Prompt Contract (prompts.py), validates the raw
response into ReadingResponse (schemas.py), and runs it through
rag/guardrails.py before handing it back to the API layer.

Reuses the same google-genai client pattern as app/rag/gemini_client.py
(kept separate rather than modified, since that module still backs the
existing /chat numerology+zodiac feature and should not be disturbed by
this new structured-output path).
"""

from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from app.astrology.schemas import CalculationWarning
from app.rag.guardrails import GuardrailReport, check_response
from app.rag.retriever import RetrievedChunk
from app.rag.schemas import AtomicFact

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import ReadingResponse

DEFAULT_MODEL = "gemini-2.5-flash"


class ReadingInterpreter:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def interpret(
        self,
        question: str,
        facts: list[AtomicFact],
        chunks: list[RetrievedChunk],
        calculation_warnings: list[CalculationWarning] | None = None,
    ) -> tuple[ReadingResponse, GuardrailReport]:
        user_prompt = build_user_prompt(question, facts, chunks, calculation_warnings)

        response = self.client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)
        reading = ReadingResponse.model_validate(raw)
        report = check_response(reading, facts, chunks)
        return reading, report
