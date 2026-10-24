"""
app.astrology
-------------
Deterministic Thai-astrology Calculation Engine.

Hard rule (see docs/thai_astrology_rag_implementation_spec.docx section 2, 18):
  This package MUST NOT call any LLM and MUST NOT guess a formula that has no
  verified source_reference. Every rule table exposed here carries a
  `source_reference` (see schemas.SourceReference) and, where a formula is not
  yet verified against a primary text, the function raises
  `FormulaNotVerifiedError` instead of returning a guessed value.
"""

from .errors import FormulaNotVerifiedError

__all__ = ["FormulaNotVerifiedError"]
