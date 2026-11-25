"""Reading FAIRsharing policy records: the parsers, the live route over a mocked transport, the
committed snapshot and the factory."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from dd_agent_advisor_policy import factory
from dd_agent_advisor_policy.advise import ModelAdvisor
from dd_agent_advisor_policy.crossref import CrossrefJournals
from dd_agent_advisor_policy.explain import TemplateExplainer
from dd_agent_advisor_policy.live import PolicyLive
from dd_agent_advisor_policy.opf import OpenPolicyFinder
from dd_agent_advisor_policy.records import from_api_json, from_public_json
from dd_agent_advisor_policy.ror import RorDump, RorLive
from dd_agent_advisor_policy.snapshot import SNAPSHOT, PolicySnapshot
from dd_sdk.credentials import ConfigError
from dd_sdk.registry import Query, RegistryUnavailable

DATA = Path(__file__).with_name("data")
PUBLIC = json.loads((DATA / "FAIRsharing.e081af.public.json").read_text(encoding="utf-8"))
API = json.loads((DATA / "FAIRsharing.e081af.api.json").read_text(encoding="utf-8"))
# Settings that run without a model, for the tests that are not about the model.
TEMPLATE = {"DD_POLICY_ADVISOR": "template"}


# --- parsers ----------------------------------------------------------------------------------


def test_a_policy_record_keeps_its_clauses_and_no_contacts() -> None:
    record = from_public_json(PUBLIC)
    assert record is not None
    assert (record.fairsharing_id, record.policy_type) == ("FAIRsharing.e081af", "institution")
    assert record.clause("sharing_data").values["mandated_data_sharing"] == "suggested"
    assert record.clause("data_availability_statement").values["required"] == "yes"
    assert record.year_creation == "2020"
    assert "contacts" not in json.dumps(record.document())


def test_both_routes_give_the_same_document_when_there_are_no_relations() -> None:
    public, api = from_public_json(PUBLIC), from_api_json(API["data"])
    assert public is not None and api is not None
    assert public.document() == api.document()
    assert public.content_hash() == api.content_hash()


def test_relations_are_read_from_the_api_and_sorted() -> None:
    data = copy.deepcopy(API["data"])
    data["attributes"]["linked_records"] = [
        {
            "linked_record_name": "Zeta Archive",
            "linked_record_id": 9,
            "linked_record_registry": "Database",
            "linked_record_type": "repository",
            "relation": "recommends",
        },
        {
            "linked_record_name": "Alpha Archive",
            "linked_record_id": 8,
            "linked_record_registry": "Database",
            "linked_record_type": "repository",
            "relation": "requires",
        },
    ]
    record = from_api_json(data)
    assert record is not None
    assert [(r.relation, r.name, r.numeric_id) for r in record.relations] == [
        ("recommends", "Zeta Archive", "9"),
        ("requires", "Alpha Archive", "8"),
    ]


def test_a_record_from_another_registry_is_not_a_policy() -> None:
    assert from_public_json({**PUBLIC, "registry": "Database"}) is None


# --- live route -------------------------------------------------------------------------------


def _live(handler: Any, login: str | None = "me", password: str | None = "secret") -> PolicyLive:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PolicyLive(client=client, login=login, password=password)


def test_live_search_signs_in_and_asks_for_policies_only() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/users/sign_in":
            return httpx.Response(200, json={"jwt": "token"})
        return httpx.Response(200, json={"data": [API["data"]]})

    records = _live(handler).search(Query(text="University of Sheffield"))
    assert [r.fairsharing_id for r in records] == ["FAIRsharing.e081af"]
    search = seen[-1]
    assert search.url.params["fairsharing_registry"] == "policy"
    assert search.headers["Authorization"] == "Bearer token"


def test_live_search_without_an_account_is_unavailable_not_empty() -> None:
    live = _live(lambda req: httpx.Response(500), login=None, password=None)
    with pytest.raises(RegistryUnavailable, match="needs an account"):
        live.search(Query(text="x"))


def test_live_fetch_with_an_account_reads_the_api_record() -> None:
    paths: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        if req.url.path == "/users/sign_in":
            return httpx.Response(200, json={"jwt": "token"})
        if req.url.host == "fairsharing.org":
            return httpx.Response(200, json=PUBLIC)
        return httpx.Response(200, json=API)

    record = _live(handler).fetch("FAIRsharing.e081af")
    assert record is not None and record.numeric_id == "5035"
    assert paths == ["/FAIRsharing.e081af", "/users/sign_in", "/fairsharing_records/5035"]


def test_live_fetch_of_an_unknown_identifier_is_none() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})

    assert _live(handler, login=None, password=None).fetch("FAIRsharing.nope") is None


def test_a_transport_failure_is_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(RegistryUnavailable):
        _live(handler).fetch("FAIRsharing.e081af")


# --- snapshot ---------------------------------------------------------------------------------


def test_the_snapshot_matches_its_manifest_and_is_labelled_by_kind() -> None:
    manifest = json.loads(SNAPSHOT.with_name("manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() == manifest["sha256"]
    snapshot = PolicySnapshot()
    assert len(snapshot.records) == manifest["records"]
    assert (
        snapshot.snapshot_ref().label
        == f"fairsharing-policy:snapshot:{manifest['fetched_at'][:10]}"
    )
    for record in snapshot.records:
        # Each line is the record's document as hashed (docs/specs/agents.md).
        assert record.document() == json.loads(json.dumps(record.document()))


def test_the_snapshot_finds_a_policy_by_name() -> None:
    names = [r.fairsharing_id for r in PolicySnapshot().search(Query(text="ESRC"))]
    assert "FAIRsharing.636kdn" in names


# --- factory ----------------------------------------------------------------------------------


def test_the_factory_defaults_to_the_snapshot_and_the_model_advisor() -> None:
    agent = factory.build({"ANTHROPIC_API_KEY": "k"})
    assert isinstance(agent.sources.policies, PolicySnapshot)
    assert isinstance(agent.explainer, ModelAdvisor)
    assert agent.explainer.max_lookups == 6
    assert (
        isinstance(agent.sources.organisations, RorDump)
        and agent.sources.organisations_fallback is None
    )
    assert isinstance(agent.sources.crossref, CrossrefJournals) and agent.sources.opf is None
    [model] = agent.spec.models
    assert model.model == agent.explainer.model_id and model.tools


def test_without_a_model_key_the_error_says_how_to_run_without_a_model() -> None:
    with pytest.raises(ConfigError, match="DD_POLICY_ADVISOR=template"):
        factory.build({})


def test_the_template_needs_no_key_and_declares_no_model() -> None:
    agent = factory.build(TEMPLATE)
    assert isinstance(agent.explainer, TemplateExplainer)
    assert agent.spec.models == ()


def test_the_older_switch_still_turns_the_model_off() -> None:
    agent = factory.build({"DD_POLICY_EXPLAINER": "template"})
    assert isinstance(agent.explainer, TemplateExplainer)


def test_open_policy_finder_is_searched_only_with_a_key(tmp_path: Path) -> None:
    assert factory.build(TEMPLATE).sources.opf is None
    assert isinstance(
        factory.build({**TEMPLATE, "OPEN_POLICY_FINDER_API_KEY": "k"}).sources.opf, OpenPolicyFinder
    )
    (tmp_path / "opf").write_text("k\n", encoding="utf-8")
    agent = factory.build(
        {
            **TEMPLATE,
            "OPEN_POLICY_FINDER_API_KEY_FILE": "opf",
            "CREDENTIALS_DIRECTORY": str(tmp_path),
        }
    )
    assert isinstance(agent.sources.opf, OpenPolicyFinder)


def test_without_an_open_policy_finder_key_start_up_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=factory.__name__):
        factory.build(TEMPLATE)
    assert any(factory.OPF_KEY in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=factory.__name__):
        factory.build({**TEMPLATE, factory.OPF_KEY: "k"})
    assert not any(factory.OPF_KEY in r.getMessage() for r in caplog.records)


def test_crossref_can_be_turned_off_and_the_lookups_limited() -> None:
    agent = factory.build(
        {"ANTHROPIC_API_KEY": "k", "DD_POLICY_CROSSREF": "off", "DD_POLICY_MAX_LOOKUPS": "0"}
    )
    assert agent.sources.crossref is None
    assert isinstance(agent.explainer, ModelAdvisor) and agent.explainer.max_lookups == 0


def test_crossref_is_sent_the_operators_contact_address_only_when_one_is_set() -> None:
    seen: list[httpx.Request] = []

    def keep(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404)

    for contact in (None, "ops@example.org"):
        # A given client is identified too: the header is sent with each request.
        client = httpx.Client(transport=httpx.MockTransport(keep))
        assert CrossrefJournals(client, contact=contact).by_issn("2052-4463") is None
    without, with_contact = (r.headers["user-agent"] for r in seen)
    assert without.startswith("data-director-advisor-policy/") and "mailto:" not in without
    assert with_contact.startswith("data-director-advisor-policy/")
    assert "mailto:ops@example.org" in with_contact
    built = factory.build({**TEMPLATE, "DD_REGISTRY_CONTACT": " ops@example.org "})
    assert isinstance(built.sources.crossref, CrossrefJournals)
    assert built.sources.crossref.user_agent == with_contact
    unset = factory.build({**TEMPLATE, "DD_REGISTRY_CONTACT": ""})
    assert isinstance(unset.sources.crossref, CrossrefJournals)
    assert unset.sources.crossref.user_agent == without


def test_live_ror_falls_back_to_the_built_dump() -> None:
    agent = factory.build({**TEMPLATE, "DD_POLICY_ROR": "live"})
    assert isinstance(agent.sources.organisations, RorLive)
    assert isinstance(agent.sources.organisations_fallback, RorDump)


def test_live_retrieval_needs_an_account_and_falls_back_to_the_snapshot() -> None:
    with pytest.raises(ConfigError, match="FAIRSHARING_LOGIN"):
        factory.build({**TEMPLATE, "DD_POLICY_RETRIEVAL": "live"})
    agent = factory.build(
        {
            **TEMPLATE,
            "DD_POLICY_RETRIEVAL": "live",
            "FAIRSHARING_LOGIN": "me",
            "FAIRSHARING_PASSWORD": "pw",
        }
    )
    assert isinstance(agent.sources.policies, PolicyLive)
    assert isinstance(agent.sources.fallback, PolicySnapshot)


def test_the_password_may_be_a_credential_file(tmp_path: Path) -> None:
    (tmp_path / "fairsharing").write_text("pw\n", encoding="utf-8")
    agent = factory.build(
        {
            **TEMPLATE,
            "DD_POLICY_RETRIEVAL": "live",
            "FAIRSHARING_LOGIN": "me",
            "FAIRSHARING_PASSWORD_FILE": "fairsharing",
            "CREDENTIALS_DIRECTORY": str(tmp_path),
        }
    )
    assert isinstance(agent.sources.policies, PolicyLive) and agent.sources.policies.signed_in


def test_the_anthropic_explainer_declares_its_model() -> None:
    agent = factory.build({"DD_POLICY_EXPLAINER": "anthropic", "ANTHROPIC_API_KEY": "k"})
    assert isinstance(agent.explainer, ModelAdvisor)
    assert [m.model for m in agent.spec.models] == [agent.explainer.model_id]


@pytest.mark.parametrize(
    "env",
    [
        {**TEMPLATE, "DD_POLICY_RETRIEVAL": "both"},
        {**TEMPLATE, "DD_POLICY_ROR": "both"},
        {**TEMPLATE, "DD_POLICY_CROSSREF": "maybe"},
        {**TEMPLATE, "DD_REGISTRY_CONTACT": "not an address"},
        {**TEMPLATE, "DD_REGISTRY_CONTACT": "ops@example.org)\r\nX-Other: 1"},
        {"DD_POLICY_ADVISOR": "magic"},
        {"DD_POLICY_EXPLAINER": "magic"},
        {"DD_POLICY_EXPLAINER": "anthropic"},
        {"DD_POLICY_ADVISOR": "model", "ANTHROPIC_API_KEY": "k", "DD_POLICY_MAX_LOOKUPS": "many"},
    ],
)
def test_bad_configuration_stops_at_start_up(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        factory.build(env)


@pytest.mark.parametrize(
    ("settings", "declared"),
    [
        (
            {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "m-1", "OPENAI_API_KEY": "k"},
            ("openai", "m-1", "hosted"),
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "llama",
                "DD_MODEL_BASE_URL": "http://localhost:11434/v1",
            },
            ("localhost:11434", "llama", "local"),
        ),
    ],
)
def test_the_model_can_come_from_another_provider(
    settings: dict[str, str], declared: tuple[str, str, str]
) -> None:
    pytest.importorskip("openai")
    agent = factory.build({"DD_POLICY_EXPLAINER": "model", **settings})
    assert [(m.provider, m.model, m.hosting) for m in agent.spec.models] == [declared]


def test_the_older_anthropic_setting_names_only_anthropic() -> None:
    with pytest.raises(ConfigError):
        factory.build(
            {
                "DD_POLICY_EXPLAINER": "anthropic",
                "DD_MODEL_PROVIDER": "openai",
                "DD_MODEL_ID": "m-1",
                "OPENAI_API_KEY": "k",
            }
        )


# --- Open Policy Finder's licence and credit ---------------------------------------------------


def test_open_policy_finder_is_documented_with_its_licence_and_credited() -> None:
    from dd_agent_advisor_policy.report import LIMITATIONS

    source = (DATA.parent.parent / "data" / "open-policy-finder" / "SOURCE.md").read_text(
        encoding="utf-8"
    )
    assert "CC BY-NC-ND 4.0" in source
    assert any(
        "Jisc Open Policy Finder" in line and "CC BY-NC-ND 4.0" in line for line in LIMITATIONS
    )
