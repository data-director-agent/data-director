"""The grounding linter over hand-built span trees and envelope documents, one mode at a time.

No conductor, no agent: these tests pin the rules themselves, including the regression that
motivated ADR-0008 — a payload the linter does not recognise must fail, never pass.
"""

from __future__ import annotations

from typing import Any

import pytest

from dd_sdk.contract.models import input_source_id
from dd_sdk.tracing import (
    ATTR_CONTENT_HASH,
    ATTR_GROUNDING_MODE,
    ATTR_INPUT_HASH,
    ATTR_SOURCE_ID,
    CHAT,
    INVOKE_AGENT,
    RETRIEVAL,
    SpanRecord,
)
from workbench import grounding

INV = "01a06cdb-985f-7375-9aa2-37be29f0f2a8"
INPUT_HASH = "1" * 64
H_A, H_B = "a" * 64, "b" * 64


def span(
    name: str, span_id: str, start: int, end: int, parent: str | None = "root", **attrs: Any
) -> SpanRecord:
    return SpanRecord(
        name=name,
        span_id=span_id,
        parent_id=parent,
        trace_id="t",
        start_ns=start,
        end_ns=end,
        attributes=attrs,
    )


def root(mode: str) -> SpanRecord:
    return span(
        INVOKE_AGENT,
        "root",
        0,
        100,
        parent=None,
        **{ATTR_GROUNDING_MODE: mode, ATTR_INPUT_HASH: INPUT_HASH},
    )


def retrieval(span_id: str, source_id: str, content_hash: str, start: int = 10) -> SpanRecord:
    return span(
        RETRIEVAL,
        span_id,
        start,
        start + 5,
        **{ATTR_SOURCE_ID: source_id, ATTR_CONTENT_HASH: content_hash},
    )


def chat(start: int = 50) -> SpanRecord:
    return span(CHAT, "chat", start, start + 5)


def envelope(
    mode: str, payload: dict[str, Any] | None, evidence: list[tuple[str, str]]
) -> dict[str, Any]:
    return {
        "invocation_id": INV,
        "grounding_mode": mode,
        "outcome": {"status": "succeeded" if payload is not None else "abstained"},
        "payload": payload,
        "evidence": [{"source_id": s, "content_hash": h} for s, h in evidence],
    }


def ref(source_id: str, content_hash: str) -> dict[str, str]:
    return {"source_id": source_id, "content_hash": content_hash}


def violations(report: grounding.GroundingReport, prefix: str) -> list[str]:
    return [v for v in report.violations if v.startswith(prefix)]


# --- G0: structure ------------------------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD")
def test_payload_without_grounded_on_is_a_violation_not_a_pass() -> None:
    """The regression: an unrecognised payload shape used to make G2/G3 silently no-op."""
    records = [root("retrieval"), retrieval("r1", "S", H_A)]
    env = envelope("retrieval", {"schema_class": "Mystery", "items": [{"id": "X"}]}, [("S", H_A)])
    report = grounding.lint(records, env)
    assert not report.passed
    assert any("lacks grounded_on" in v for v in violations(report, "G0"))


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD")
def test_payload_without_schema_class_is_a_violation() -> None:
    records = [root("retrieval"), retrieval("r1", "S", H_A)]
    env = envelope("retrieval", {"grounded_on": [ref("S", H_A)]}, [("S", H_A)])
    report = grounding.lint(records, env)
    assert any("lacks schema_class" in v for v in violations(report, "G0"))


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_envelope_mode_must_match_the_root_span() -> None:
    records = [root("none")]
    env = envelope("input_only", None, [])
    report = grounding.lint(records, env)
    assert any("root span carries 'none'" in v for v in violations(report, "G0"))


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_missing_or_unknown_mode_fails() -> None:
    records = [root("retrieval")]
    assert not grounding.lint(records, envelope("telepathy", None, [])).passed
    env = envelope("retrieval", None, [])
    del env["grounding_mode"]
    report = grounding.lint(records, env)
    assert not report.passed and report.mode is None


def test_exactly_one_root_span() -> None:
    report = grounding.lint([], envelope("none", None, []))
    assert not report.passed and "expected exactly one invoke_agent" in report.violations[0]


def test_malformed_grounding_reference_is_a_violation() -> None:
    records = [root("retrieval"), retrieval("r1", "S", H_A)]
    env = envelope(
        "retrieval", {"schema_class": "P", "grounded_on": [{"source_id": "S"}]}, [("S", H_A)]
    )
    assert any("malformed" in v for v in violations(grounding.lint(records, env), "G0"))


# --- retrieval ----------------------------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDING", "DD-GROUNDING-MODE")
def test_retrieval_mode_passes_when_everything_was_retrieved_and_cited() -> None:
    records = [root("retrieval"), retrieval("r1", "S", H_A), retrieval("r2", "T", H_B), chat()]
    payload = {
        "schema_class": "P",
        "grounded_on": [ref("S", H_A)],
        "parts": [{"grounded_on": [ref("T", H_B)]}],  # nested: walked at any depth
    }
    report = grounding.lint(records, envelope("retrieval", payload, [("S", H_A), ("T", H_B)]))
    assert report.passed, report.violations
    assert (report.retrieval_count, report.chat_count) == (2, 1)


@pytest.mark.requirement("DD-GROUNDING")
def test_g1_chat_before_or_without_retrieval() -> None:
    env = envelope("retrieval", None, [])
    early = [root("retrieval"), chat(start=5), retrieval("r1", "S", H_A, start=10)]
    assert violations(grounding.lint(early, env), "G1")
    alone = [root("retrieval"), chat()]
    assert (
        "G1: a chat span exists but no retrieval span does" in grounding.lint(alone, env).violations
    )


@pytest.mark.requirement("DD-GROUNDING")
def test_g2_asserted_identity_must_match_a_retrieval_on_id_and_hash() -> None:
    records = [root("retrieval"), retrieval("r1", "S", H_A)]
    smuggled = {"schema_class": "P", "grounded_on": [ref("S", H_A), ref("X", H_A)]}
    report = grounding.lint(records, envelope("retrieval", smuggled, [("S", H_A)]))
    assert any("'X'" in v for v in violations(report, "G2"))
    wrong_hash = {"schema_class": "P", "grounded_on": [ref("S", H_B)]}
    report = grounding.lint(records, envelope("retrieval", wrong_hash, [("S", H_A)]))
    assert violations(report, "G2")


@pytest.mark.requirement("DD-GROUNDING")
def test_g2_succeeded_payload_resting_on_nothing() -> None:
    records = [root("retrieval"), retrieval("r1", "S", H_A)]
    report = grounding.lint(
        records, envelope("retrieval", {"schema_class": "P", "grounded_on": []}, [("S", H_A)])
    )
    assert any("rests on nothing" in v for v in violations(report, "G2"))


@pytest.mark.requirement("DD-GROUNDING")
def test_g3_and_g4_evidence_agrees_with_trace_and_payload() -> None:
    records = [root("retrieval"), retrieval("r1", "S", H_A)]
    payload = {"schema_class": "P", "grounded_on": [ref("S", H_A)]}
    # Evidence cites something never retrieved.
    report = grounding.lint(records, envelope("retrieval", payload, [("S", H_A), ("Z", H_B)]))
    assert violations(report, "G3")
    # Evidence omits something the payload rests on.
    report = grounding.lint(records, envelope("retrieval", payload, []))
    assert violations(report, "G4")


# --- input_only and none ------------------------------------------------------------------------


def input_grounded_payload() -> dict[str, Any]:
    return {"schema_class": "P", "grounded_on": [ref(input_source_id(INV), INPUT_HASH)]}


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_input_only_permits_chat_without_retrieval() -> None:
    records = [root("input_only"), chat()]
    env = envelope("input_only", input_grounded_payload(), [(input_source_id(INV), INPUT_HASH)])
    report = grounding.lint(records, env)
    assert report.passed, report.violations


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_input_only_forbids_retrieval_and_foreign_citations() -> None:
    env = envelope("input_only", input_grounded_payload(), [(input_source_id(INV), INPUT_HASH)])
    assert violations(grounding.lint([root("input_only"), retrieval("r1", "S", H_A)], env), "R1")
    foreign = {"schema_class": "P", "grounded_on": [ref("S", H_A)]}
    report = grounding.lint([root("input_only")], envelope("input_only", foreign, [("S", H_A)]))
    assert len(violations(report, "R2")) == 2  # payload and evidence
    wrong_hash = {"schema_class": "P", "grounded_on": [ref(input_source_id(INV), H_B)]}
    report = grounding.lint([root("input_only")], envelope("input_only", wrong_hash, []))
    assert violations(report, "R2") and violations(report, "R3")


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_none_mode_forbids_chat() -> None:
    env = envelope("none", input_grounded_payload(), [(input_source_id(INV), INPUT_HASH)])
    assert grounding.lint([root("none")], env).passed
    assert violations(grounding.lint([root("none"), chat()], env), "N1")


# --- delegation (ADR-0012) ----------------------------------------------------------------------

CHILD = "01a06cdb-985f-7375-9aa2-37be29f0f2a9"
H_CHILD = "c" * 64


def delegation_envelope(
    grounded_on: list[dict[str, str]], evidence: list[tuple[str, str]]
) -> dict[str, Any]:
    env = envelope("delegation", {"schema_class": "Reply", "grounded_on": grounded_on}, evidence)
    env["delegations"] = [
        {
            "delegated_invocation_id": CHILD,
            "delegated_agent_id": "hello.world",
            "delegated_agent_version": "0.1.0",
            "delegated_status": "succeeded",
            "content_hash": H_CHILD,
        }
    ]
    return env


INPUT_PAIR = (input_source_id(INV), INPUT_HASH)
CHILD_PAIR = (f"invocation:{CHILD}", H_CHILD)


@pytest.mark.requirement("DD-DELEGATION")
def test_delegation_mode_passes_citing_input_and_a_recorded_child() -> None:
    env = delegation_envelope([ref(*INPUT_PAIR), ref(*CHILD_PAIR)], [INPUT_PAIR, CHILD_PAIR])
    report = grounding.lint([root("delegation"), chat()], env)  # a model call is allowed
    assert report.passed, report.violations


@pytest.mark.requirement("DD-DELEGATION")
def test_delegation_mode_rejects_an_unrecorded_or_altered_child() -> None:
    other = (f"invocation:{INV[:-1]}0", H_CHILD)
    report = grounding.lint(
        [root("delegation")],
        delegation_envelope([ref(*INPUT_PAIR), ref(*other)], [INPUT_PAIR, other]),
    )
    assert violations(report, "D1") and violations(report, "D2")
    altered = (CHILD_PAIR[0], H_A)
    report = grounding.lint(
        [root("delegation")],
        delegation_envelope([ref(*INPUT_PAIR), ref(*altered)], [INPUT_PAIR, altered]),
    )
    assert violations(report, "D1") and violations(report, "D2")


@pytest.mark.requirement("DD-DELEGATION")
def test_delegation_mode_forbids_retrieval_and_requires_the_input() -> None:
    env = delegation_envelope([ref(*INPUT_PAIR)], [INPUT_PAIR])
    assert violations(grounding.lint([root("delegation"), retrieval("r1", "S", H_A)], env), "R1")
    report = grounding.lint(
        [root("delegation")], delegation_envelope([ref(*CHILD_PAIR)], [CHILD_PAIR])
    )
    assert violations(report, "D3")
    report = grounding.lint(
        [root("delegation")], delegation_envelope([ref(*CHILD_PAIR)], [INPUT_PAIR])
    )
    assert violations(report, "G4")


def test_summary_names_the_mode() -> None:
    report = grounding.lint([root("none")], envelope("none", None, []))
    assert report.summary().startswith("grounding: passed [none]")
