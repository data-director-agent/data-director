"""A person's own model account end to end (docs/specs/model-accounts.md; issue #867).

The real conductor mints a model grant from the profile's `model_accounts`, and the real model
orchestrator, built from its own settings, calls through the real model broker. The broker is
served in process, and its calls to the provider are replayed from a cassette. Each of the other
tests stands in for one of these; this one joins them, to show that the run records whose account
paid, that a missing account ends the run as an outcome, and that a person's key reaches no record.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from starlette.testclient import TestClient

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model import factory
from dd_broker.agents import AgentCredentials
from dd_broker.app import Broker
from dd_broker.app import build_app as build_broker
from dd_broker.grants import GrantVerifier, HarnessKeys, TicketVerifier
from dd_broker.store import Store
from dd_harness.conductor import Conductor
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, GrantKeys, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    Message,
    ModelAccount,
    OutcomeStatus,
    ReasonCode,
    Reply,
)
from dd_sdk.tracing import ATTR_MODEL_ACCOUNT

AGENT = "orchestrator.model"
BROKER_URL = "http://broker.test"
# Distinctive enough that finding any of them anywhere means it leaked.
OWN_KEY = "sk-ant-api03-sentinel-867-own-3f9a1c"
DEPLOYMENT_KEY = "sk-ant-api03-sentinel-867-deployment-b7e2"
CREDENTIAL = "broker-credential-sentinel-867-5d0c"


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    # The conductor, its agents and the broker are served in memory; only the broker's calls to
    # the provider come from the cassette. The query is not matched (see the orchestrator's own
    # cassette test, from which this cassette is copied).
    def provider_calls_only(request: Any) -> Any:
        return None if request.host.endswith(".test") else request

    return {
        **vcr_config,
        "before_record_request": provider_calls_only,
        "match_on": ["method", "scheme", "host", "port", "path"],
    }


@pytest.fixture
def default_cassette_name() -> str:
    # Every case replays the same three answers; a refused call never reaches them.
    return "orchestrator_greets_ada"


class ToBroker(httpx2.BaseTransport):
    """The orchestrator's Claude client's transport: each request goes to the broker served in
    memory, as it would over the host's loopback interface."""

    def __init__(self, broker: TestClient) -> None:
        self.broker = broker

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        answer = self.broker.request(
            request.method,
            str(request.url),
            headers=[(k.decode(), v.decode()) for k, v in request.headers.raw],
            content=request.read(),
        )
        return httpx2.Response(
            answer.status_code, headers=answer.headers.multi_items(), content=answer.content
        )


@dataclass
class Deployment:
    conductor: Conductor
    store: Store
    runs: Path
    keys: GrantKeys

    def enrol(self) -> None:
        """The person signed in adds their own Anthropic key, as the Profile page would."""
        minter = self.conductor.model_grants
        assert minter is not None
        self.store.put(minter.pseudonym(TEST_PRINCIPAL), "anthropic", OWN_KEY, label="…3f9a")

    def greet(self) -> Any:
        return self.conductor.invoke(
            request(AGENT, Message(message_text="Please greet Ada")), acting_for=TEST_PRINCIPAL
        )


def own_profile(tmp_path: Path, own: str, fallback: str) -> Path:
    path = tmp_path / "own.yaml"
    path.write_text(
        PERMISSIVE.read_text(encoding="utf-8")
        + f"model_accounts:\n  own: {own}\n  fallback: {fallback}\n"
        + "  providers:\n    - provider: anthropic\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Build a deployment whose profile sets `own` and `fallback`."""
    opened: list[TestClient] = []

    def build(own: str, fallback: str) -> Deployment:
        keys = GrantKeys()
        minter = keys.minter()
        store = Store(tmp_path / "broker" / "broker.sqlite3", os.urandom(32))
        verifier_keys = HarnessKeys(minter.jwks)
        broker = Broker(
            store=store,
            verifier=GrantVerifier(verifier_keys, keys.subject_key),
            tickets=TicketVerifier(verifier_keys, keys.subject_key, store),
            agents=AgentCredentials({AGENT: hashlib.sha256(CREDENTIAL.encode()).hexdigest()}),
            deployment_keys={"anthropic": DEPLOYMENT_KEY},
        )
        client = TestClient(build_broker(broker), base_url=BROKER_URL)
        client.__enter__()
        opened.append(client)
        # Only a client built for the broker uses this: the SDK makes one for a brokered endpoint.
        default = anthropic.DefaultHttpxClient
        monkeypatch.setattr(
            anthropic, "DefaultHttpxClient", lambda: default(transport=ToBroker(client))
        )
        orchestrator = factory.build(
            {"DD_MODEL_BROKER_URL": BROKER_URL, "DD_MODEL_BROKER_CREDENTIAL": CREDENTIAL}
        )
        runs = tmp_path / "runs"
        conductor = make_conductor(
            runs,
            orchestrator,
            HelloWorld(),
            crate=True,
            profile=own_profile(tmp_path, own, fallback),
            model_grants=minter,
            model_broker=True,
        )
        return Deployment(conductor, store, runs, keys)

    yield build
    for client in opened:
        client.__exit__(None, None, None)


def stored_text(runs: Path) -> str:
    return "\n".join(
        p.read_bytes().decode("utf-8", "replace") for p in sorted(runs.rglob("*")) if p.is_file()
    )


def crate_accounts(runs: Path, invocation_id: str) -> list[str]:
    crate = json.loads(
        (runs / invocation_id / "crate" / "ro-crate-metadata.json").read_text(encoding="utf-8")
    )
    by_id = {e["@id"]: e for e in crate["@graph"]}
    return [
        by_id[e["additionalProperty"]["@id"]]["value"]
        for e in crate["@graph"]
        if "additionalProperty" in e
    ]


def span_accounts(runs: Path, invocation_id: str) -> list[str]:
    spans = (runs / invocation_id / "spans.jsonl").read_text(encoding="utf-8").splitlines()
    return [
        span["attributes"][ATTR_MODEL_ACCOUNT]
        for span in map(json.loads, spans)
        if ATTR_MODEL_ACCOUNT in span.get("attributes", {})
    ]


def assert_no_secret_anywhere(deployment: Deployment, env: Any) -> None:
    text = stored_text(deployment.runs) + json.dumps(env.to_document())
    text += json.dumps(describe(deployment.conductor.registry.get(AGENT).spec))  # type: ignore[union-attr]
    for secret in (OWN_KEY, DEPLOYMENT_KEY, CREDENTIAL):
        assert secret not in text
    # Nor the pseudonym, by which the broker alone knows the person.
    minter = deployment.conductor.model_grants
    assert minter is not None
    assert minter.pseudonym(TEST_PRINCIPAL) not in text


@pytest.mark.vcr
@pytest.mark.requirement("DD-DELEGATION")
def test_an_enrolled_own_account_pays_and_the_run_says_so(deploy: Any) -> None:
    deployment = deploy("allowed", "deployment")
    deployment.enrol()

    env = deployment.greet()

    assert env.outcome.status is OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.payload_as(Reply).reply_text == "The greeting agent says: Hello, Ada!"
    assert [d.delegated_agent_id for d in env.delegations] == ["example.hello"]
    # The two reply turns and the title, each paid for by the person's own account.
    assert [c.model_account for c in env.telemetry.model_calls] == [ModelAccount.OWN] * 3
    assert crate_accounts(deployment.runs, env.invocation_id) == [ModelAccount.OWN.value] * 3
    assert set(span_accounts(deployment.runs, env.invocation_id)) == {ModelAccount.OWN.value}
    assert deployment.store.usage(deployment.conductor.model_grants.pseudonym(TEST_PRINCIPAL))
    assert_no_secret_anywhere(deployment, env)


@pytest.mark.vcr
def test_with_no_account_the_deployment_pays_when_the_profile_lets_it(deploy: Any) -> None:
    deployment = deploy("allowed", "deployment")

    env = deployment.greet()

    assert env.outcome.status is OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert [c.model_account for c in env.telemetry.model_calls] == [ModelAccount.DEPLOYMENT] * 3
    assert crate_accounts(deployment.runs, env.invocation_id) == [ModelAccount.DEPLOYMENT.value] * 3
    assert set(span_accounts(deployment.runs, env.invocation_id)) == {ModelAccount.DEPLOYMENT.value}
    assert_no_secret_anywhere(deployment, env)


@pytest.mark.vcr
def test_with_no_account_when_one_is_required_the_run_ends_as_an_outcome(deploy: Any) -> None:
    deployment = deploy("required", "none")

    env = deployment.greet()

    assert env.outcome.status is OutcomeStatus.ABSTAINED, env.outcome.statement
    assert env.outcome.reason_code is ReasonCode.MODEL_ACCOUNT_MISSING
    # Refused before the provider was called: nobody paid for anything.
    assert env.telemetry.model_calls == []
    assert env.delegations == []
    assert_no_secret_anywhere(deployment, env)


@pytest.mark.vcr
def test_without_the_operators_statement_the_agent_is_not_called(
    deploy: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test goes through the broker only because the operator says the agent does: without
    that statement the conductor refuses the agent before calling it (#819)."""
    deployment = deploy("allowed", "deployment")
    deployment.enrol()
    agent = deployment.conductor.registry.get(AGENT)
    monkeypatch.setattr(agent, "model_broker", False)

    env = deployment.greet()

    assert env.outcome.status is OutcomeStatus.FAILED
    assert env.telemetry.model_calls == []
