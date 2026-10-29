"""The model key stays in the process that calls the model (ADR-0026, #43): a run of the
Anthropic explainer, replayed from a cassette, leaves the key in no envelope, span, RO-Crate or
manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_standards import factory
from dd_agent_advisor_standards import testing as fakes
from dd_agent_advisor_standards.classes import Recommendations
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.agent import describe
from dd_sdk.contract.models import Derivation, OutcomeStatus

# Distinctive enough that finding it anywhere means it leaked.
SENTINEL = "sk-ant-sentinel-7f3c9a1e5b2d4086"


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    # The conductor reaches agents served in memory under `*.agents.test`; only the model call
    # comes from the cassette.
    def model_calls_only(request: Any) -> Any:
        return None if request.host.endswith(".agents.test") else request

    return {**vcr_config, "before_record_request": model_calls_only}


@pytest.mark.vcr
def test_the_key_reaches_no_stored_record(runs_dir: Path) -> None:
    pytest.importorskip("anthropic")
    built = factory.build({"DD_STANDARDS_EXPLAINER": "anthropic", "ANTHROPIC_API_KEY": SENTINEL})
    built.retrieval = fakes.FakeRetrieval()
    conductor = fakes.make_conductor(runs_dir, standards=built, crate=True)

    env = conductor.invoke(fakes.request("advisor.standards"), acting_for=TEST_PRINCIPAL)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    # The cassette was replayed: the rationales came from the model.
    payload = env.payload_as(Recommendations)
    assert any(i.rationale_derivation == Derivation.MODEL for i in payload.items)
    stored = [p for p in runs_dir.rglob("*") if p.is_file()]
    assert any(p.name == "ro-crate-metadata.json" for p in stored)
    for path in stored:
        assert SENTINEL.encode() not in path.read_bytes(), f"the key is in {path}"
    assert SENTINEL not in json.dumps(env.to_document())
    assert SENTINEL not in json.dumps(describe(built.spec))
