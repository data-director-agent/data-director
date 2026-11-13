"""Whose model account paid for each call, and how a run ends when a person's own account cannot
be used (docs/specs/model-accounts.md, invariants 9 and 10).

The model broker answers every call with `X-DD-Model-Account` (`own` or `deployment`), and a
refusal with `X-DD-Reason`. The client `dd_sdk.model_anthropic.anthropic_client` builds for the
broker reads the first header into this context (`report`) as each answer arrives. The call's
`chat` span (`record_account`) and its `ModelCall` (`dd_sdk.prompts.ModelCallLog.record`) take it
from there, so an agent that calls its client directly records whose account paid without reading
a header itself. A call that did not go through the broker was paid for by the deployment's key.

While an agent runs, `dd_sdk.serve` collects every call it records (`bind_run`). If the agent then
raises because the broker refused a person's own account (`refusal`), the run ends `abstained`
with the matching reason code and the calls made before the refusal (`accounted`), rather than as
an exception. Nothing here sees a key, a label or a pseudonym.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.trace import Span

from dd_sdk.agent import AgentResult
from dd_sdk.contract.models import ModelAccount, ModelCall, Outcome, OutcomeStatus, ReasonCode
from dd_sdk.model_grant import HEADER_ACCOUNT, HEADER_REASON
from dd_sdk.tracing import ATTR_MODEL_ACCOUNT

# The broker's reason codes for a person's own account (`dd_broker.reasons`), and the run's.
REFUSALS: dict[str, ReasonCode] = {
    "model-account-missing": ReasonCode.MODEL_ACCOUNT_MISSING,
    "model-account-rejected": ReasonCode.MODEL_ACCOUNT_REJECTED,
    "model-account-limit": ReasonCode.MODEL_ACCOUNT_LIMIT,
}

STATEMENTS: dict[ReasonCode, str] = {
    ReasonCode.MODEL_ACCOUNT_MISSING: (
        "This needs your own AI account, and none is set up. Add one on your Profile page."
    ),
    ReasonCode.MODEL_ACCOUNT_REJECTED: (
        "Your AI provider refused your account's key. Replace it on your Profile page."
    ),
    ReasonCode.MODEL_ACCOUNT_LIMIT: (
        "Your AI provider reported a usage or rate limit on your account. Try again later."
    ),
}

# Whose account paid for the call most recently answered in this context, if the broker said.
_PAYER: ContextVar[ModelAccount | None] = ContextVar("dd_model_payer", default=None)


@dataclass
class RunCalls:
    """Every model call one run records, and the prompts they name, in the order made."""

    calls: list[ModelCall] = field(default_factory=list)
    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)


_RUN: ContextVar[RunCalls | None] = ContextVar("dd_model_run", default=None)


def report(headers: Any) -> None:
    """Note whose account paid, from the broker's answer's headers. Called by the brokered
    client for every answer; an answer without the header changes nothing."""
    value = headers.get(HEADER_ACCOUNT)
    if value is None:
        return
    try:
        _PAYER.set(ModelAccount(value))
    except ValueError:
        return


def current() -> ModelAccount:
    """Whose account paid for the call just answered: the broker's word, or the deployment's when
    the call did not go through the broker."""
    return _PAYER.get() or ModelAccount.DEPLOYMENT


def take() -> ModelAccount:
    """`current()`, and forget it, so that the next call is not recorded with this one's payer."""
    payer = current()
    _PAYER.set(None)
    return payer


def record_account(span: Span) -> ModelAccount:
    """Set `dd.model_account` on a `chat` span from the call just answered, and return it."""
    payer = current()
    span.set_attribute(ATTR_MODEL_ACCOUNT, payer.value)
    return payer


def collect(call: ModelCall, prompt: dict[str, Any]) -> None:
    """Add a recorded call to the run in progress, if one is bound."""
    run = _RUN.get()
    if run is not None:
        run.calls.append(call)
        run.prompts[call.prompt_digest] = prompt


@contextmanager
def bind_run() -> Iterator[RunCalls]:
    """Collect every model call recorded until the block ends."""
    run = RunCalls()
    token = _RUN.set(run)
    payer = _PAYER.set(None)
    try:
        yield run
    finally:
        _PAYER.reset(payer)
        _RUN.reset(token)


def refusal(exc: BaseException) -> ReasonCode | None:
    """The reason code, if `exc` or an exception it was raised from is the broker refusing a
    person's own account. Read from the answer's `X-DD-Reason`, by duck typing, so that this
    module imports no provider's SDK."""
    seen: set[int] = set()
    current_exc: BaseException | None = exc
    while current_exc is not None and id(current_exc) not in seen:
        seen.add(id(current_exc))
        response = getattr(current_exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            reason = REFUSALS.get(str(headers.get(HEADER_REASON, "")))
            if reason is not None:
                return reason
        current_exc = current_exc.__cause__ or current_exc.__context__
    return None


def accounted(run: Callable[[], AgentResult]) -> AgentResult:
    """Run an agent; if it raises because a person's own account could not be used, end the run
    `abstained` with the reason code and the calls made before, instead. Any other exception
    propagates."""
    with bind_run() as calls:
        try:
            return run()
        except Exception as exc:
            reason = refusal(exc)
            if reason is None:
                raise
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=STATEMENTS[reason]
                ),
                model_calls=tuple(calls.calls),
                prompts=dict(calls.prompts),
            )
