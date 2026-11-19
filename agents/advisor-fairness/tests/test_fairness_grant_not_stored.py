"""Neither the model grant nor the agent's broker credential is kept anywhere
(docs/specs/model-accounts.md, invariants 6 and 8): a run whose writer call goes through the
broker leaves them in no envelope, span, run store, RO-Crate or agent card. Modelled on
advisor-documentation's `test_grant_not_stored.py`; the broker is answered in memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_fairness import factory
from dd_agent_advisor_fairness.classes import FairnessReport, PublishedRecord
from dd_agent_advisor_fairness.testing import writer_reply
from dd_agent_advisor_fairness.write import ModelWriter
from dd_harness.testing import TEST_PRINCIPAL, GrantKeys, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Derivation, OutcomeStatus, to_document
from dd_sdk.credentials import ConfigError, model_endpoint
from dd_sdk.model_anthropic import AnthropicModel, anthropic_client
from dd_sdk.model_grant import HEADER_GRANT, ModelGrantClaims

MODEL = "claude-test"
BROKER = "http://broker.test:8790"
# Distinctive enough that finding it anywhere means it leaked.
SENTINEL = "dd-broker-sentinel-7c2f90a4e1d65b38"
ENV = {
    factory.SWITCH: "anthropic",
    "DD_MODEL_ID": MODEL,
    "DD_MODEL_BROKER_URL": BROKER,
    "DD_MODEL_BROKER_CREDENTIAL": SENTINEL,
}
ASKED = PublishedRecord(title="Household energy use in Sheffield, 2024", keywords=["energy"])
TAILORED = "Ask the repository to mint a DOI for the household energy data."


class Broker:
    """Answers the Messages API as the broker does, keeping what each request carried."""

    def __init__(self) -> None:
        self.headers: list[dict[str, str]] = []

    def __call__(self, request: Any) -> Any:
        httpx = pytest.importorskip("httpx2")
        self.headers.append(dict(request.headers))
        text = writer_reply([("identifier-is-doi", TAILORED)])
        return httpx.Response(
            200,
            headers={"X-DD-Model-Account": "deployment", "X-DD-Model-Provider": "anthropic"},
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 40},
            },
        )


def test_a_missing_broker_credential_stops_the_agent_at_start_up() -> None:
    env = {k: v for k, v in ENV.items() if k != "DD_MODEL_BROKER_CREDENTIAL"}
    with pytest.raises(ConfigError):
        factory.build(env)


def test_the_grant_and_the_credential_reach_no_stored_record(runs_dir: Path) -> None:
    pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx2")
    # Built as `main` builds it: the credential is read once, from the environment.
    built = factory.build(ENV)
    broker = Broker()
    built.writer = ModelWriter(
        AnthropicModel(
            MODEL,
            client=anthropic_client(
                model_endpoint(ENV), http_client=httpx.Client(transport=httpx.MockTransport(broker))
            ),
        )
    )
    keys = GrantKeys()
    conductor = make_conductor(runs_dir, built, crate=True, model_grants=keys.minter())

    env = conductor.invoke(request("advisor.fairness", ASKED), acting_for=TEST_PRINCIPAL)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [doi] = [c for c in env.payload_as(FairnessReport).checks if c.check == "identifier-is-doi"]
    assert (doi.recommendation, doi.recommendation_derivation) == (TAILORED, Derivation.MODEL)
    [sent] = broker.headers
    assert SENTINEL in (
        sent.get("x-api-key"),
        sent.get("authorization", "").removeprefix("Bearer "),
    )
    grant = sent[HEADER_GRANT.lower()]
    claims = ModelGrantClaims.from_claims(keys.open(grant).claims)
    assert (claims.agent, claims.invocation) == ("advisor.fairness", env.invocation_id)

    stored = [p for p in runs_dir.rglob("*") if p.is_file()]
    assert any(p.name == "ro-crate-metadata.json" for p in stored)
    for secret in (SENTINEL, grant):
        for path in stored:
            assert secret.encode() not in path.read_bytes(), f"a secret is in {path}"
        assert secret not in json.dumps(to_document(env))
        assert secret not in json.dumps(describe(built.spec))
