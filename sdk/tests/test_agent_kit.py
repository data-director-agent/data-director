"""The agent kit: the abstention and the input citation every agent builds (`dd_sdk.agent`)."""

from __future__ import annotations

from datetime import UTC, datetime

from opentelemetry.sdk.trace import TracerProvider

from dd_sdk.agent import RunContext, abstain, input_evidence, input_ref
from dd_sdk.contract.models import OutcomeStatus, ReasonCode
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION


def _ctx() -> RunContext:
    return RunContext(
        tracer=TracerProvider().get_tracer("test"), input_ref="input:abc", input_hash="a" * 64
    )


def test_abstain_carries_the_reason_and_nothing_else() -> None:
    reason = next(iter(ReasonCode))
    result = abstain(reason, "Not mine to answer.")
    assert result.outcome.status is OutcomeStatus.ABSTAINED
    assert result.outcome.reason_code is reason
    assert result.outcome.statement == "Not mine to answer."
    assert result.payload is None
    assert result.evidence == []


def test_input_ref_cites_the_input() -> None:
    ref = input_ref(_ctx())
    assert ref.source_id == "input:abc"
    assert ref.content_hash == "a" * 64


def test_input_evidence_matches_the_ref() -> None:
    ctx = _ctx()
    before = datetime.now(UTC)
    item = input_evidence(ctx)
    ref = input_ref(ctx)
    assert (item.source_id, item.content_hash) == (ref.source_id, ref.content_hash)
    assert item.hash_algorithm == HASH_ALGORITHM
    assert item.canonicalisation == INPUT_CANONICALISATION
    assert item.retrieved_at is not None and item.retrieved_at >= before


def test_input_evidence_takes_a_pinned_time() -> None:
    when = datetime(2026, 1, 2, tzinfo=UTC)
    assert input_evidence(_ctx(), retrieved_at=when).retrieved_at == when
