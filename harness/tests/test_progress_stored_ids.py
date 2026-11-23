"""A project log outlives the release that wrote it: the steps and questions it names may since
have been retired (docs/specs/projects.md), and reading it never fails for that
(`dd_harness.progress`, `dd_sdk.process_flow.current_step`)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dd_harness import intake, progress
from dd_sdk import process_flow
from dd_sdk.intake import INTAKE, NO, NOT_SURE, YES
from dd_sdk.process_flow import STEPS

# Ids a log may hold: this release's, and any a contract pattern allows (a retired id, or one a
# later release wrote before a rollback).
STEP_IDS = st.one_of(
    st.sampled_from(sorted(STEPS)), st.from_regex(r"[a-z]+\.[a-z-]+", fullmatch=True)
)
QUESTION_IDS = st.one_of(
    st.sampled_from([q.id for q in INTAKE]), st.from_regex(r"intake\.[a-z-]+", fullmatch=True)
)
EVENTS = st.one_of(
    st.builds(
        lambda s, m: {"event": progress.STEP_MARKED, "step_id": s, "mark": m},
        STEP_IDS,
        st.sampled_from(progress.MARKS),
    ),
    st.builds(
        lambda q, v: {"event": progress.INTAKE_ANSWERED, "question_id": q, "answer_values": [v]},
        QUESTION_IDS,
        st.sampled_from([YES, NO, NOT_SURE]),
    ),
    st.builds(
        lambda n: {"event": progress.ENTRY_CHOSEN, "entry": n},
        st.sampled_from([e.number for e in process_flow.ENTRIES]),
    ),
)


@given(st.lists(EVENTS, max_size=12))
def test_any_stored_id_reads_and_only_live_steps_show(log: list[dict[str, Any]]) -> None:
    assert progress.step_states(log).keys() <= STEPS
    assert progress.step_reasons(log).keys() <= STEPS
    assert progress.intake_answers(log).keys() <= {q.id for q in INTAKE}
    intake.describe(log)


def test_a_mark_of_a_retired_step_counts_for_its_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(process_flow.RETIRED_STEPS, "setup.terms", "preparation.vocabularies")
    log = [{"event": progress.STEP_MARKED, "step_id": "setup.terms", "mark": "done"}]
    assert progress.step_states(log) == {"preparation.vocabularies": "done"}
