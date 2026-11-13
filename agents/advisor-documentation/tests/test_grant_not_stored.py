"""Neither the model grant nor the agent's broker credential is kept anywhere
(docs/specs/model-accounts.md, invariants 6 and 8): a run whose model call goes through the broker
leaves them in no envelope, span, run store, RO-Crate or agent card. Modelled on
advisor-standards' `test_key_not_stored.py`; the broker is answered in memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_documentation import factory
from dd_agent_advisor_documentation.prose import AnthropicWriter
from dd_harness.testing import TEST_PRINCIPAL, GrantKeys, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DraftRequest,
    OutcomeStatus,
    to_document,
)
from dd_sdk.credentials import ConfigError, model_endpoint
from dd_sdk.model_anthropic import anthropic_client
from dd_sdk.model_grant import HEADER_GRANT, ModelGrantClaims

SAMPLES = Path(__file__).with_name("data")
MODEL = "claude-test"
BROKER = "http://broker.test:8790"
# Distinctive enough that finding it anywhere means it leaked.
SENTINEL = "dd-broker-sentinel-3b8e61c0d94f2a75"
OVERVIEW = "Soil nitrate readings from three survey sites, one row per sample."
ENV = {
    "DD_DOCUMENTATION_WRITER": "anthropic",
    "DD_MODEL_ID": MODEL,
    "DD_MODEL_BROKER_URL": BROKER,
    "DD_MODEL_BROKER_CREDENTIAL": SENTINEL,
}


class Broker:
    """Answers the Messages API as the broker does, keeping what each request carried."""

    def __init__(self) -> None:
        self.headers: list[dict[str, str]] = []

    def __call__(self, request: Any) -> Any:
        httpx = pytest.importorskip("httpx2")
        self.headers.append(dict(request.headers))
        return httpx.Response(
            200,
            headers={"X-DD-Model-Account": "deployment", "X-DD-Model-Provider": "anthropic"},
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [{"type": "text", "text": json.dumps({"overview": OVERVIEW})}],
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
    built.writer = AnthropicWriter(
        client=anthropic_client(
            model_endpoint(ENV), http_client=httpx.Client(transport=httpx.MockTransport(broker))
        ),
        model_id=MODEL,
    )
    keys = GrantKeys()
    conductor = make_conductor(runs_dir, built, crate=True, model_grants=keys.minter())
    asked = DraftRequest.model_validate_json(
        (SAMPLES / "soil-survey.readme.draft.json").read_text(encoding="utf-8")
    )

    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.payload_as(Document).document_derivation == Derivation.MODEL
    # The call went to the broker with the agent's credential and a grant for this run.
    [sent] = broker.headers
    assert SENTINEL in (
        sent.get("x-api-key"),
        sent.get("authorization", "").removeprefix("Bearer "),
    )
    grant = sent[HEADER_GRANT.lower()]
    claims = ModelGrantClaims.from_claims(keys.open(grant).claims)
    assert (claims.agent, claims.invocation) == ("advisor.documentation", env.invocation_id)

    stored = [p for p in runs_dir.rglob("*") if p.is_file()]
    assert any(p.name == "ro-crate-metadata.json" for p in stored)
    for secret in (SENTINEL, grant):
        for path in stored:
            assert secret.encode() not in path.read_bytes(), f"a secret is in {path}"
        assert secret not in json.dumps(to_document(env))
        assert secret not in json.dumps(describe(built.spec))
