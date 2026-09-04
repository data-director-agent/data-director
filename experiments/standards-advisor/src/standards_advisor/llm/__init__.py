"""Model access — one narrow interface (§1.4)."""

from standards_advisor.llm.provider import DEFAULT_MODEL_ID, get_model
from standards_advisor.llm.structured import StructuredResult, call_structured

__all__ = ["DEFAULT_MODEL_ID", "StructuredResult", "call_structured", "get_model"]
