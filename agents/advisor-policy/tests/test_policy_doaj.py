"""The policy advisor with DOAJ and no Open Policy Finder key, through the conductor, without a
model (#1517): an open access journal is identified, its DOAJ record is matched as its policy, and
its publisher's FAIRsharing policy is reached; DOAJ off, down or ambiguous is said, not hidden."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_policy_agent import FakePolicies, invoke

from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    PolicyChecks,
    PolicyContext,
    PolicyRegistry,
)
from dd_agent_advisor_policy.doaj import DoajJournals
from dd_agent_advisor_policy.factory import build_doaj
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.search import Sources
from dd_agent_advisor_policy.tools import Lookups
from dd_mcp_doaj.journals import Doaj
from dd_sdk.contract.models import OutcomeStatus, ReasonCode
from dd_sdk.credentials import ConfigError
from dd_sdk.evidence import verify

DATA = Path(__file__).with_name("data")
PLOS_DOAJ = "https://doaj.org/toc/1932-6203"
PLOS_POLICY = PolicyRecord(
    fairsharing_id="FAIRsharing.test-plos",
    name="Public Library of Science (PLoS) - Data Availability",
    policy_type="journal_publisher",
    subjects=["Subject Agnostic"],
)
BY_ISSN = Actor(role=ActorRole.JOURNAL, name="PLOS ONE", issn="1932-6203")
BY_TITLE = Actor(role=ActorRole.JOURNAL, name="PLOS ONE")


def plos() -> dict[str, Any]:
    body: dict[str, Any] = json.loads((DATA / "doaj-plos.json").read_text(encoding="utf-8"))
    return body


def doaj(handler: Callable[[httpx.Request], httpx.Response] | None = None) -> DoajJournals:
    def answer(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=plos())

    client = httpx.Client(transport=httpx.MockTransport(handler or answer))
    return DoajJournals(Doaj(client=client, sleep=lambda _: None))


def twice(_: httpx.Request) -> httpx.Response:
    """Two journals with the same title, as DOAJ might list them."""
    body = plos()
    other = json.loads(json.dumps(body["results"][0]))
    other["id"], other["bibjson"]["eissn"] = "another", "1234-5679"
    body["results"].append(other)
    return httpx.Response(200, json=body)


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_without_a_key_an_open_access_journal_is_found_in_doaj(runs_dir: Path) -> None:
    advisor = PolicyAgent(Sources(FakePolicies([PLOS_POLICY]), doaj=doaj()))
    env = invoke(runs_dir, PolicyContext(actors=[BY_ISSN]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    registries = {p.grounded_on[0].source_id: p.registry for p in checks.policies}
    # The journal's DOAJ record, and its publisher's FAIRsharing policy reached by DOAJ's name.
    assert registries == {
        PLOS_DOAJ: PolicyRegistry.DOAJ,
        PLOS_POLICY.fairsharing_id: PolicyRegistry.FAIRSHARING,
    }
    [journal] = checks.journals
    assert journal.issn == "1932-6203" and journal.publisher
    assert [g.source_id for g in journal.grounded_on] == [PLOS_DOAJ]
    evidence = {e.source_id: e for e in env.evidence}
    assert (evidence[PLOS_DOAJ].snapshot_ref or "").startswith("doaj-journals:live:")
    content = evidence[PLOS_DOAJ].content
    assert content is not None
    assert verify(content, evidence[PLOS_DOAJ].canonicalisation, evidence[PLOS_DOAJ].content_hash)
    assert [n.registry for n in checks.not_searched] == [PolicyRegistry.OPEN_POLICY_FINDER]


def test_a_journal_given_by_title_is_found_in_doaj(runs_dir: Path) -> None:
    advisor = PolicyAgent(Sources(FakePolicies([]), doaj=doaj()))
    env = invoke(runs_dir, PolicyContext(actors=[BY_TITLE]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [p.registry for p in checks.policies] == [PolicyRegistry.DOAJ]
    assert checks.journals[0].issn == "1932-6203"


@pytest.mark.requirement("DD-OUTCOME")
def test_two_doaj_journals_of_one_title_ask_which(runs_dir: Path) -> None:
    advisor = PolicyAgent(Sources(FakePolicies([PLOS_POLICY]), doaj=doaj(twice)))
    env = invoke(runs_dir, PolicyContext(actors=[BY_TITLE]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert checks.policies == []
    [ambiguous] = checks.ambiguous
    assert ambiguous.actor == BY_TITLE.name and len(ambiguous.grounded_on) == 2


@pytest.mark.requirement("DD-OUTCOME")
def test_doaj_off_is_named_and_a_journal_found_nowhere_could_not_be_searched(
    runs_dir: Path,
) -> None:
    env = invoke(runs_dir, PolicyContext(actors=[BY_ISSN]), PolicyAgent(Sources(FakePolicies([]))))
    assert env.outcome.status == OutcomeStatus.ABSTAINED, env.outcome.statement
    assert env.outcome.reason_code == ReasonCode.REGISTRY_UNAVAILABLE


def test_doaj_down_is_noted_and_fairsharing_still_answers(runs_dir: Path) -> None:
    advisor = PolicyAgent(
        Sources(FakePolicies([PLOS_POLICY]), doaj=doaj(lambda _: httpx.Response(503)))
    )
    named = Actor(role=ActorRole.JOURNAL, name="Public Library of Science (PLoS)")
    env = invoke(runs_dir, PolicyContext(actors=[named]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [p.registry for p in checks.policies] == [PolicyRegistry.FAIRSHARING]
    assert "HTTP 503" in env.outcome.statement


def test_the_model_may_search_doaj_only_when_it_is_on() -> None:
    names = {t.name for t in Lookups(doaj=doaj()).tools()}
    assert {"search_doaj", "get_journal_by_issn"} <= names
    assert "search_doaj" not in {t.name for t in Lookups().tools()}


def test_doaj_is_on_by_default_and_can_be_turned_off() -> None:
    assert build_doaj({}) is not None
    assert build_doaj({"DD_POLICY_DOAJ": "off"}) is None
    with pytest.raises(ConfigError):
        build_doaj({"DD_POLICY_DOAJ": "sometimes"})
