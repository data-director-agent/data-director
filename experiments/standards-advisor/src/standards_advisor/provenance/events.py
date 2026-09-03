"""The event log — a LangChain callback handler writing `events.jsonl`.

This is the half of the audit trail that graph state cannot supply. `run_id` and `parent_run_id`
come free on every callback, so the log carries the call tree without any extra plumbing, and
`AIMessage.usage_metadata` gives token counts that never enter state at all.

LangSmith is deliberately not used for this. `langsmith` is an unavoidable dependency of
`langchain-core`, but with `LANGSMITH_TRACING` unset and no key present nothing is exported
anywhere — the trace stays on this machine, which is the point for a tool whose argument is
local-first handling of research data (§1.4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler

from standards_advisor.ids import utc_now

if TYPE_CHECKING:
    from langchain_core.outputs import LLMResult

    from standards_advisor.provenance.run_dir import RunDirectory

# Characters of a prompt or response body kept in an event. The full prompt text is copied into
# the run directory separately, so this is for correlation rather than for the record.
BODY_EXCERPT_CHARS = 2000


class ProvenanceHandler(BaseCallbackHandler):
    """Writes model and chain activity to a run's append-only event log."""

    raise_error = False
    """A failure inside the audit trail must not take down the run it is recording."""

    def __init__(self, run_dir: RunDirectory) -> None:
        self.run_dir = run_dir
        self.token_totals: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        self.model_calls = 0

    # -- helpers -------------------------------------------------------------------------

    def _emit(self, event_type: str, **fields: Any) -> None:
        payload: dict[str, Any] = {
            "at": utc_now().isoformat(),
            "event": event_type,
            "run_id": self.run_dir.run_id,
        }
        payload.update({key: value for key, value in fields.items() if value is not None})
        self.run_dir.append_event(payload)

    @staticmethod
    def _excerpt(text: str) -> str:
        if len(text) <= BODY_EXCERPT_CHARS:
            return text
        return text[:BODY_EXCERPT_CHARS] + f"… [{len(text)} chars total]"

    # -- model events --------------------------------------------------------------------

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.model_calls += 1
        rendered = "\n\n".join(
            str(getattr(message, "content", message)) for batch in messages for message in batch
        )
        self._emit(
            "chat_model_start",
            call_id=str(run_id),
            parent_id=str(parent_run_id) if parent_run_id else None,
            model=(metadata or {}).get("ls_model_name"),
            provider=(metadata or {}).get("ls_provider"),
            invocation_params=_stringify(kwargs.get("invocation_params")),
            prompt_excerpt=self._excerpt(rendered),
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        usage: dict[str, int] = {}
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                metadata = getattr(message, "usage_metadata", None) or {}
                for key in ("input_tokens", "output_tokens"):
                    value = metadata.get(key)
                    if isinstance(value, int):
                        usage[key] = usage.get(key, 0) + value
                        self.token_totals[key] = self.token_totals.get(key, 0) + value

        text = "".join(
            getattr(generation, "text", "")
            for generations in response.generations
            for generation in generations
        )
        self._emit(
            "llm_end",
            call_id=str(run_id),
            parent_id=str(parent_run_id) if parent_run_id else None,
            usage=usage or None,
            response_excerpt=self._excerpt(text) if text else None,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._emit(
            "llm_error",
            call_id=str(run_id),
            parent_id=str(parent_run_id) if parent_run_id else None,
            error=f"{type(error).__name__}: {error}",
        )

    # -- chain events --------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = kwargs.get("name") or (serialized or {}).get("name")
        self._emit(
            "chain_start",
            call_id=str(run_id),
            parent_id=str(parent_run_id) if parent_run_id else None,
            name=name,
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._emit(
            "chain_end",
            call_id=str(run_id),
            parent_id=str(parent_run_id) if parent_run_id else None,
            name=kwargs.get("name"),
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._emit(
            "chain_error",
            call_id=str(run_id),
            parent_id=str(parent_run_id) if parent_run_id else None,
            error=f"{type(error).__name__}: {error}",
        )

    # -- our own events ------------------------------------------------------------------

    def note(self, kind: str, detail: str, **fields: Any) -> None:
        """Record something the framework does not know about.

        Used for the things that are *outcomes* rather than faults: a structured response that
        would not parse, a recommendation dropped by the grounding check, a rule skipped for
        want of an input.
        """
        self._emit("note", kind=kind, detail=detail, **fields)


def _stringify(value: Any) -> dict[str, str] | None:
    """Reduce invocation parameters to strings, so the log stays JSON-safe."""
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}
