"""Structured model output, with a parse failure treated as data.

`with_structured_output(..., include_raw=True)` is used rather than the raising form for two
reasons that both come from the architecture rather than from taste. C12 needs the raw response
kept even when it could not be parsed — that is exactly the case a later reader most wants to
see. And a node that raises on a malformed response destroys the run's audit trail at the point
where it is most informative, which contradicts §5.5's position that a run producing nothing is
still a good run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langchain_core.runnables import RunnableConfig

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    """A structured call's outcome. Exactly one of `parsed` and `parse_error` is set."""

    parsed: T | None
    raw: BaseMessage | None
    parse_error: str | None

    @property
    def ok(self) -> bool:
        return self.parsed is not None

    def usage(self) -> dict[str, int]:
        """Token usage from the raw message, for the provenance record. Empty if absent."""
        if self.raw is None:
            return {}
        metadata = getattr(self.raw, "usage_metadata", None) or {}
        return {
            key: int(value)
            for key, value in metadata.items()
            if key in {"input_tokens", "output_tokens", "total_tokens"}
            and isinstance(value, int | float)
        }


def call_structured[T: BaseModel](
    model: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage] | list[tuple[str, str]],
    config: RunnableConfig | None = None,
) -> StructuredResult[T]:
    """Invoke `model`, coercing its answer into `schema`.

    Never raises for a malformed response; returns a `StructuredResult` carrying the raw
    message and the error text so both can be recorded.
    """
    structured = model.with_structured_output(schema, include_raw=True)
    try:
        result: Any = structured.invoke(messages, config=config)
    except Exception as exc:  # noqa: BLE001 — a transport failure is data too, not a crash
        return StructuredResult(parsed=None, raw=None, parse_error=f"{type(exc).__name__}: {exc}")

    if not isinstance(result, dict):
        # A provider that ignores include_raw. Accept the parsed value and record the surprise.
        if isinstance(result, schema):
            return StructuredResult(parsed=result, raw=None, parse_error=None)
        return StructuredResult(
            parsed=None,
            raw=None,
            parse_error=f"unexpected structured-output shape: {type(result).__name__}",
        )

    error = result.get("parsing_error")
    parsed = result.get("parsed")
    raw = result.get("raw")
    if error is not None or parsed is None:
        detail = str(error) if error is not None else "model returned no parsed value"
        return StructuredResult(parsed=None, raw=raw, parse_error=detail)
    return StructuredResult(parsed=parsed, raw=raw, parse_error=None)
