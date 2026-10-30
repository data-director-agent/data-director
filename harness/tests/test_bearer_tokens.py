"""A person established from an OpenID Connect ID token (ADR-0029, #151): the token is verified,
the principal recorded as authenticated with the issuer that vouched, and a caller without a good
token refused rather than given a default. The provider is `FakeIdentityProvider`: no network."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from a2a.helpers import get_data_parts
from a2a.types import TaskState
from starlette.applications import Starlette

from dd_harness.identity import (
    MIN_REFETCH_S,
    BearerTokenAuthenticator,
    IdentityError,
    IssuerKeys,
    OperatorAssertion,
    Unauthenticated,
    checked_configuration,
    fetch_configuration,
    fetch_keys,
    verify_id_token,
)
from dd_harness.settings import Settings, build_authenticator
from dd_harness.testing import (
    PERMISSIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    FakeIdentityProvider,
    ScriptedAgent,
    grant_token,
    make_conductor,
    message,
    request,
    review_of_input,
    send_to_harness,
)
from dd_harness.transport.a2a import a2a_routes
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    Assurance,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    to_document,
)
from dd_sdk.wire import META_DELEGATION_TOKEN

ORCID_ID = "0000-0002-1825-0097"
OTHER_ID = "0000-0001-5109-3700"
URL = "http://harness.test"


@pytest.fixture(scope="module")
def idp() -> FakeIdentityProvider:
    return FakeIdentityProvider()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def failure(task: Any) -> dict[str, Any]:
    """What a failed A2A task reports."""
    assert task.status.state == TaskState.TASK_STATE_FAILED
    reported: dict[str, Any] = get_data_parts(task.status.message.parts)[0]
    return reported


# --- Verifying a token --------------------------------------------------------------------------


@pytest.mark.requirement("DD-ACTS-FOR")
def test_a_verified_token_names_an_authenticated_person(idp: FakeIdentityProvider) -> None:
    person = verify_id_token(
        idp.id_token(ORCID_ID, nonce="n-1"), idp.provider, idp.keys(), nonce="n-1"
    )
    assert person.principal_id == f"https://sandbox.orcid.org/{ORCID_ID}"
    assert person.name == "Josiah Carberry"
    assert person.assurance == Assurance.AUTHENTICATED
    assert person.vouched_by == "https://sandbox.orcid.org"


@pytest.mark.parametrize(
    ("claims", "name"),
    [
        ({"name": None, "given_name": "Josiah", "family_name": "Carberry"}, "Josiah Carberry"),
        ({"name": "  ", "family_name": "Carberry"}, "Carberry"),
        ({"name": None}, f"https://sandbox.orcid.org/{ORCID_ID}"),
    ],
)
def test_the_name_falls_back_to_the_parts_then_the_id(
    idp: FakeIdentityProvider, claims: dict[str, Any], name: str
) -> None:
    token = idp.id_token(ORCID_ID, **claims)
    assert verify_id_token(token, idp.provider, idp.keys()).name == name


@pytest.mark.requirement("DD-ACTS-FOR")
@pytest.mark.parametrize(
    "spoil",
    [
        pytest.param({"issued_at": int(time.time()) - 3600}, id="expired"),
        pytest.param({"audience": "APP-SOMEONEELSE"}, id="another-audience"),
        pytest.param({"audience": ["APP-SOMEONEELSE", "APP-TESTCLIENT0000"]}, id="azp-missing"),
        pytest.param({"issuer": "https://orcid.example"}, id="another-issuer"),
        pytest.param({"nonce": "replayed"}, id="wrong-nonce"),
        pytest.param({"sub": ""}, id="no-subject"),
    ],
)
def test_a_spoilt_token_is_refused(idp: FakeIdentityProvider, spoil: dict[str, Any]) -> None:
    token = idp.id_token(**{"nonce": "n-1", **spoil})
    with pytest.raises(Unauthenticated) as refused:
        verify_id_token(token, idp.provider, idp.keys(), nonce="n-1")
    assert token not in str(refused.value)


def test_a_token_with_several_audiences_is_for_the_party_it_names(
    idp: FakeIdentityProvider,
) -> None:
    token = idp.id_token(audience=["APP-OTHER", idp.client_id], azp=idp.client_id)
    assert verify_id_token(token, idp.provider, idp.keys()).vouched_by == idp.issuer


def test_a_token_signed_with_an_unknown_key_is_refused(idp: FakeIdentityProvider) -> None:
    stranger = FakeIdentityProvider(key=FakeIdentityProvider().key)
    with pytest.raises(Unauthenticated):
        verify_id_token(stranger.id_token(), idp.provider, idp.keys())
    with pytest.raises(Unauthenticated):
        verify_id_token("not.a.token", idp.provider, idp.keys())


def test_a_rotated_key_is_fetched_once_and_not_on_every_unknown_key() -> None:
    idp = FakeIdentityProvider()
    keys = idp.keys()
    verify_id_token(idp.id_token(), idp.provider, keys)
    assert idp.fetches == 1
    verify_id_token(idp.id_token(), idp.provider, keys)
    assert idp.fetches == 1  # cached
    old = idp.key
    idp.rotate("fake-2")
    # A key the cache does not hold is fetched, but not more often than MIN_REFETCH_S.
    with pytest.raises(Unauthenticated):
        verify_id_token(idp.id_token(), idp.provider, keys)
    assert idp.fetches == 1
    keys._fetched_at -= MIN_REFETCH_S
    assert verify_id_token(idp.id_token(), idp.provider, keys).vouched_by == idp.issuer
    assert idp.fetches == 2
    with pytest.raises(Unauthenticated):  # the old key is no longer published
        verify_id_token(idp.id_token(key=old), idp.provider, keys)


def test_keys_that_cannot_be_fetched_refuse_the_caller(idp: FakeIdentityProvider) -> None:
    def unreachable(issuer: str) -> dict[str, Any]:
        raise ValueError("no route to host")

    keys = IssuerKeys(idp.issuer, fetch=unreachable)
    with pytest.raises(Unauthenticated, match="could not be fetched"):
        verify_id_token(idp.id_token(), idp.provider, keys)


def test_the_keys_are_found_through_the_discovery_document(idp: FakeIdentityProvider) -> None:
    transport = idp.transport()
    configuration = fetch_configuration(idp.issuer, transport=transport)
    assert configuration["token_endpoint"] == f"{idp.issuer}/oauth/token"
    keys = IssuerKeys(idp.issuer, fetch=lambda issuer: fetch_keys(issuer, transport=transport))
    assert verify_id_token(idp.id_token(), idp.provider, keys).vouched_by == idp.issuer


@pytest.mark.parametrize(
    "change",
    [{"issuer": "https://orcid.org"}, {"token_endpoint": None}, {"jwks_uri": 7}],
    ids=["another issuer", "no token endpoint", "no key set"],
)
def test_a_discovery_document_for_another_issuer_or_without_endpoints_is_refused(
    idp: FakeIdentityProvider, change: dict[str, Any]
) -> None:
    document = {**idp.discovery(), **change}
    with pytest.raises(ValueError, match="discovery names"):
        checked_configuration(idp.issuer, document)


# --- The fake provider's authorisation-code flow ------------------------------------------------


def test_the_fake_provider_redeems_an_approved_code_once(idp: FakeIdentityProvider) -> None:
    query = {
        "client_id": idp.client_id,
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": "https://app.test/back",
        "state": "the-state",
        "nonce": "the-nonce",
    }
    back = idp.approve(f"{idp.issuer}/oauth/authorize?{urlencode(query)}")
    sent = parse_qs(urlsplit(back).query)
    assert back.startswith("https://app.test/back?") and sent["state"] == ["the-state"]
    form = {
        "grant_type": "authorization_code",
        "code": sent["code"][0],
        "redirect_uri": "https://app.test/back",
        "client_id": idp.client_id,
        "client_secret": idp.client_secret,
    }
    with httpx.Client(transport=idp.transport()) as client:
        answer = client.post(f"{idp.issuer}/oauth/token", data=form)
        again = client.post(f"{idp.issuer}/oauth/token", data=form)
        wrong = client.post(f"{idp.issuer}/oauth/token", data={**form, "client_secret": "no"})
    principal = verify_id_token(
        answer.json()["id_token"], idp.provider, idp.keys(), nonce="the-nonce"
    )
    assert principal.principal_id == "https://sandbox.orcid.org/0000-0002-1825-0097"
    assert again.json() == {"error": "invalid_grant"}
    assert wrong.status_code == 401


# --- The bearer-token authenticator -------------------------------------------------------------


@pytest.mark.requirement("DD-ACTS-FOR")
@pytest.mark.parametrize(
    "headers",
    [None, {}, {"authorization": "Basic dXNlcjpwYXNz"}, {"Authorization": "Bearer "}],
)
def test_a_caller_without_a_bearer_token_is_refused_not_defaulted(
    idp: FakeIdentityProvider, headers: dict[str, str] | None
) -> None:
    with pytest.raises(Unauthenticated):
        idp.authenticator().principal_for(headers)


def test_the_header_is_read_whatever_its_case(idp: FakeIdentityProvider) -> None:
    token = idp.id_token(ORCID_ID)
    for headers in (bearer(token), {"authorization": f"bearer {token}"}):
        assert idp.authenticator().principal_for(headers).principal_id.endswith(ORCID_ID)


# --- Configuration ------------------------------------------------------------------------------


def settings(**overrides: Any) -> Settings:
    base = Settings(
        runs_dir=Path("runs"),
        profile=PERMISSIVE,
        agents_config=Path("agents.yaml"),
        sources_config=Path("sources.yaml"),
    )
    return replace(base, **overrides)


def test_a_configured_provider_replaces_the_operator() -> None:
    authenticator = build_authenticator(
        settings(oidc_issuer="https://orcid.org", oidc_client_id="APP-1")
    )
    assert isinstance(authenticator, BearerTokenAuthenticator)
    assert authenticator.provider.issuer == "https://orcid.org"
    configured = settings(principal_id=TEST_PRINCIPAL.principal_id, principal_name="J")
    assert isinstance(build_authenticator(configured), OperatorAssertion)


@pytest.mark.requirement("DD-ACTS-FOR")
def test_a_provider_beside_an_operator_principal_stops_start_up() -> None:
    both = settings(
        oidc_issuer="https://orcid.org",
        oidc_client_id="APP-1",
        principal_id=TEST_PRINCIPAL.principal_id,
        principal_name=TEST_PRINCIPAL.name,
    )
    with pytest.raises(IdentityError, match="both set"):
        build_authenticator(both)
    with pytest.raises(IdentityError, match="DD_OIDC_CLIENT_ID unset"):
        build_authenticator(settings(oidc_issuer="https://orcid.org"))


def test_the_environment_names_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_OIDC_ISSUER", "https://sandbox.orcid.org")
    monkeypatch.setenv("DD_OIDC_CLIENT_ID", "APP-2")
    read = Settings.from_env(
        runs_dir=Path("runs"),
        profile=PERMISSIVE,
        agents_config=Path("a.yaml"),
        sources_config=Path("s.yaml"),
    )
    assert (read.oidc_issuer, read.oidc_client_id) == ("https://sandbox.orcid.org", "APP-2")


# --- Over A2A -----------------------------------------------------------------------------------


@pytest.mark.requirement("DD-ACTS-FOR")
def test_each_caller_is_recorded_as_the_person_their_token_names(
    idp: FakeIdentityProvider, tmp_path: Path
) -> None:
    conductor = make_conductor(tmp_path / "runs", AbstainingStub(), crate=True)
    app = Starlette(routes=a2a_routes(conductor, idp.authenticator(), URL)[1])
    for orcid in (ORCID_ID, OTHER_ID):
        token = idp.id_token(orcid)
        task = send_to_harness(app, URL, request("stub.abstain", message()), headers=bearer(token))
        assert task.status.state == TaskState.TASK_STATE_COMPLETED
    stored = sorted(e["acting_for"]["principal_id"] for e in conductor.store.iter_envelopes())
    assert stored == sorted(f"https://sandbox.orcid.org/{o}" for o in (ORCID_ID, OTHER_ID))
    for envelope in conductor.store.iter_envelopes():
        assert envelope["acting_for"]["assurance"] == "authenticated"
        assert envelope["acting_for"]["vouched_by"] == idp.issuer
    # Nothing beyond the principal's fields is kept: no token in any stored file.
    for path in (tmp_path / "runs").rglob("*"):
        if path.is_file():
            assert "eyJ" not in path.read_text(encoding="utf-8", errors="ignore"), path


@pytest.mark.requirement("DD-ACTS-FOR")
def test_a_caller_without_a_good_token_is_refused_with_the_problem(
    idp: FakeIdentityProvider, tmp_path: Path
) -> None:
    conductor = make_conductor(tmp_path / "runs", AbstainingStub())
    app = Starlette(routes=a2a_routes(conductor, idp.authenticator(), URL)[1])
    expired = idp.id_token(issued_at=int(time.time()) - 3600)
    for headers in (None, bearer(expired)):
        reported = failure(
            send_to_harness(app, URL, request("stub.abstain", message()), headers=headers)
        )
        problem = reported["problem"]
        assert problem["type"] == "https://w3id.org/data-director/problems/unauthenticated"
        assert problem["http_status"] == 401
        assert expired not in str(reported)
    assert list(conductor.store.iter_envelopes()) == []


@pytest.mark.requirement("DD-DELEGATION", "DD-ACTS-FOR")
def test_a_child_acts_for_its_parent_whoever_sends_the_callback(
    idp: FakeIdentityProvider, tmp_path: Path
) -> None:
    served: dict[str, Any] = {}

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        # The callback carries the grant and, beside it, another person's good token.
        token = {META_DELEGATION_TOKEN: grant_token(ctx)}
        served["child"] = send_to_harness(
            served["app"], URL, request("fake.none"), token, headers=bearer(idp.id_token(OTHER_ID))
        )
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.ABSTAINED,
                reason_code=ReasonCode.INSUFFICIENT_INPUT,
                statement="Called back by hand.",
            )
        )

    child = ScriptedAgent(GroundingMode.NONE, review_of_input)
    conductor = make_conductor(tmp_path, ScriptedAgent(GroundingMode.DELEGATION, behaviour), child)
    served["app"] = Starlette(routes=a2a_routes(conductor, idp.authenticator(), URL)[1])
    parent_task = send_to_harness(
        served["app"], URL, request("fake.delegation", message()), headers=bearer(idp.id_token())
    )
    assert parent_task.status.state == TaskState.TASK_STATE_COMPLETED
    assert served["child"].status.state == TaskState.TASK_STATE_COMPLETED
    envelopes = {e["agent_id"]: e for e in conductor.store.iter_envelopes()}
    parent = envelopes["fake.delegation"]["acting_for"]
    assert parent["principal_id"] == f"https://sandbox.orcid.org/{ORCID_ID}"
    assert envelopes["fake.none"]["acting_for"] == parent
    assert parent != to_document(TEST_PRINCIPAL)
