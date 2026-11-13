"""Model grants (docs/specs/model-accounts.md, The grant): the conductor mints one for each
invocation of a model-backed agent, delegated children included; the agent receives it in the A2A
metadata alone; and the broker can verify it against the harness's published keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from dd_harness import settings as harness_settings
from dd_harness.identity import OperatorAssertion
from dd_harness.model_grants import (
    JWKS_PATH,
    GrantKeyError,
    GrantMinter,
    broker_subject_key,
    jwks_routes,
    signing_key,
)
from dd_harness.settings import MODEL_GRANT_SETTINGS, SettingsError, grant_minter
from dd_harness.testing import (
    HARNESS_URL,
    TEST_PRINCIPAL,
    GrantKeys,
    ScriptedAgent,
    make_conductor,
    message,
    record,
    reply_over,
    request,
    review_of_input,
    send_to_harness,
)
from dd_harness.transport.a2a import a2a_routes
from dd_sdk.agent import AgentResult, ModelUse, RunContext
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    OutcomeStatus,
    Principal,
    PrincipalKind,
    to_document,
)
from dd_sdk.model_grant import (
    BROKER_AUDIENCE,
    META_MODEL_GRANT,
    TICKET_LIFETIME_S,
    TICKET_TYPE,
    Account,
    EnrolmentTicketClaims,
    ModelGrantClaims,
    ModelGrantError,
)

MODEL = "claude-test"
TIMEOUT_S = 30.0


@pytest.fixture(scope="module")
def keys() -> GrantKeys:
    return GrantKeys()


def model_backed(seen: list[RunContext], **overrides: Any) -> ScriptedAgent:
    """An agent whose card declares a model, and which keeps the context it was given."""

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(ctx)
        return review_of_input(req, ctx)

    overrides.setdefault("models", (ModelUse("anthropic", MODEL, "hosted"),))
    return ScriptedAgent(GroundingMode.NONE, behaviour, **overrides)


def delegating_model_backed(seen: list[RunContext], *targets: str) -> ScriptedAgent:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(ctx)
        assert ctx.delegate is not None
        return reply_over(ctx, *(ctx.delegate(t, record()) for t in targets))

    return ScriptedAgent(
        GroundingMode.DELEGATION, behaviour, models=(ModelUse("anthropic", MODEL, "hosted"),)
    )


# --- The grant ---------------------------------------------------------------------------------


def test_a_grant_has_the_shape_the_broker_checks(keys: GrantKeys) -> None:
    grant = keys.minter().mint(
        agent_id="fake.none",
        invocation_id="inv-1",
        models=[MODEL, MODEL],
        account=Account.DEPLOYMENT,
        acting_for=TEST_PRINCIPAL,
        lifetime_s=TIMEOUT_S + 0.9,
    )
    opened = keys.open(grant)

    claims = ModelGrantClaims.from_claims(opened.claims)
    assert claims.audience == BROKER_AUDIENCE
    assert (claims.agent, claims.invocation) == ("fake.none", "inv-1")
    assert claims.models == (MODEL,)
    assert claims.account == Account.DEPLOYMENT
    assert claims.expires_at - claims.issued_at <= TIMEOUT_S
    assert opened.header["alg"] in ("RS256", "ES256")
    assert opened.header["kid"] == keys.signing_key.kid
    # The pseudonym is the person's, under the harness's secret, and only the broker can read it.
    assert opened.pseudonym == keys.minter().pseudonym(TEST_PRINCIPAL)
    assert opened.pseudonym not in grant
    assert TEST_PRINCIPAL.principal_id not in json.dumps(opened.claims)


def test_no_two_grants_carry_the_same_sealed_pseudonym(keys: GrantKeys) -> None:
    minter = keys.minter()

    def mint() -> dict[str, Any]:
        grant = minter.mint(
            agent_id="fake.none",
            invocation_id="inv-1",
            models=[MODEL],
            account=Account.DEPLOYMENT,
            acting_for=TEST_PRINCIPAL,
            lifetime_s=TIMEOUT_S,
        )
        return keys.open(grant).claims

    first, second = mint(), mint()
    assert first["dd_subject"] != second["dd_subject"]


def test_an_enrolment_ticket_names_only_the_sealed_pseudonym(keys: GrantKeys) -> None:
    ticket, expires_at = keys.minter().enrolment_ticket(acting_for=TEST_PRINCIPAL)
    opened = keys.open(ticket)

    claims = EnrolmentTicketClaims.from_claims(opened.claims)
    assert claims.audience == BROKER_AUDIENCE
    assert claims.expires_at == expires_at
    assert 0 < claims.expires_at - claims.issued_at <= TICKET_LIFETIME_S
    assert opened.header["typ"] == TICKET_TYPE
    assert opened.header["kid"] == keys.signing_key.kid
    assert opened.pseudonym == keys.minter().pseudonym(TEST_PRINCIPAL)
    assert opened.pseudonym not in ticket
    assert TEST_PRINCIPAL.principal_id not in json.dumps(opened.claims)
    # A ticket is no grant.
    with pytest.raises(ModelGrantError):
        ModelGrantClaims.from_claims(opened.claims)


def test_every_ticket_is_a_different_ticket(keys: GrantKeys) -> None:
    minter = keys.minter()
    first, second = (
        keys.open(minter.enrolment_ticket(acting_for=TEST_PRINCIPAL)[0]).claims for _ in range(2)
    )
    assert first["jti"] != second["jti"]
    assert first["dd_subject"] != second["dd_subject"]


def test_the_pseudonym_is_stable_for_a_person_and_differs_between_people(
    keys: GrantKeys,
) -> None:
    minter = keys.minter()
    other = Principal(
        principal_id="https://orcid.org/0000-0001-5109-3700",
        name="Another researcher",
        principal_kind=PrincipalKind.PERSON,
    )
    assert minter.pseudonym(TEST_PRINCIPAL) == keys.minter().pseudonym(TEST_PRINCIPAL)
    assert minter.pseudonym(TEST_PRINCIPAL) != minter.pseudonym(other)
    # A different secret, a different pseudonym.
    assert GrantKeys().minter().pseudonym(TEST_PRINCIPAL) != minter.pseudonym(TEST_PRINCIPAL)


def test_the_published_keys_hold_no_private_part(keys: GrantKeys) -> None:
    jwks = keys.minter().jwks()
    [key] = jwks["keys"]
    assert key["kid"] == keys.signing_key.kid
    assert not {"d", "p", "q", "dp", "dq", "qi"} & set(key)


def test_a_signing_key_without_a_kid_is_given_its_thumbprint() -> None:
    material = GrantKeys().signing_key.as_pem(private=True).decode()
    key = signing_key(material)
    assert key.kid == key.thumbprint()


@pytest.mark.parametrize(
    "material",
    [
        "not a key",
        "{not json",
        json.dumps(GrantKeys().signing_key.as_dict(private=False)),
    ],
)
def test_an_unusable_signing_key_is_refused(material: str) -> None:
    with pytest.raises(GrantKeyError):
        signing_key(material)


def test_the_harness_takes_only_the_public_half_of_the_brokers_key(keys: GrantKeys) -> None:
    with pytest.raises(GrantKeyError):
        broker_subject_key(keys.subject_key.as_pem(private=True).decode())
    public = broker_subject_key(keys.subject_key.as_pem(private=False).decode())
    assert not public.is_private


def test_a_short_pseudonym_secret_is_refused(keys: GrantKeys) -> None:
    with pytest.raises(GrantKeyError):
        GrantMinter(keys.signing_key, keys.minter().subject_key, b"short")


# --- Settings ----------------------------------------------------------------------------------


def grant_env(keys: GrantKeys) -> dict[str, str]:
    return dict(
        zip(
            MODEL_GRANT_SETTINGS,
            (
                json.dumps(keys.signing_key.as_dict(private=True)),
                keys.subject_key.as_pem(private=False).decode(),
                keys.secret.hex(),
            ),
            strict=True,
        )
    )


def test_without_grant_settings_the_harness_mints_none() -> None:
    assert grant_minter({}) is None


def test_the_three_settings_make_a_minter(keys: GrantKeys, tmp_path: Path) -> None:
    env = grant_env(keys)
    # The signing key as a systemd credential, as a deployment supplies it.
    name = MODEL_GRANT_SETTINGS[0]
    (tmp_path / "signing").write_text(env.pop(name))
    env |= {f"{name}_FILE": "signing", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    minter = grant_minter(env)
    assert minter is not None
    assert minter.jwks() == keys.minter().jwks()


@pytest.mark.parametrize("unset", MODEL_GRANT_SETTINGS)
def test_some_but_not_all_settings_stop_start_up(keys: GrantKeys, unset: str) -> None:
    env = grant_env(keys)
    del env[unset]
    with pytest.raises(SettingsError) as caught:
        grant_minter(env)
    message = str(caught.value)
    assert unset in message and "\n" not in message
    assert keys.secret.hex() not in message


def test_an_unusable_setting_stops_start_up_without_its_value(keys: GrantKeys) -> None:
    env = grant_env(keys) | {MODEL_GRANT_SETTINGS[1]: "not a key"}
    with pytest.raises(SettingsError) as caught:
        grant_minter(env)
    assert "not a key" not in str(caught.value)
    assert keys.secret.hex() not in str(caught.value)


def test_settings_hand_the_minter_to_the_conductor(
    keys: GrantKeys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in grant_env(keys).items():
        monkeypatch.setenv(name, value)
    built = harness_settings.Settings.from_env(
        runs_dir=tmp_path,
        profile=Path("unused"),
        agents_config=Path("unused"),
        sources_config=Path("unused"),
    )
    assert built.model_grants is not None
    assert built.model_grants.jwks() == keys.minter().jwks()


# --- The conductor -----------------------------------------------------------------------------


def test_a_model_backed_agent_is_sent_a_grant_for_its_invocation(
    keys: GrantKeys, tmp_path: Path
) -> None:
    seen: list[RunContext] = []
    conductor = make_conductor(tmp_path, model_backed(seen), model_grants=keys.minter())

    env = conductor.invoke(request("fake.none", record()), acting_for=TEST_PRINCIPAL)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [ctx] = seen
    assert ctx.model_grant is not None
    claims = ModelGrantClaims.from_claims(keys.open(ctx.model_grant).claims)
    assert (claims.agent, claims.invocation) == ("fake.none", env.invocation_id)
    assert claims.models == (MODEL,)
    assert claims.expires_at - claims.issued_at <= TIMEOUT_S


def test_an_agent_that_declares_no_model_is_sent_no_grant(keys: GrantKeys, tmp_path: Path) -> None:
    seen: list[RunContext] = []
    conductor = make_conductor(tmp_path, model_backed(seen, models=()), model_grants=keys.minter())
    conductor.invoke(request("fake.none", record()), acting_for=TEST_PRINCIPAL)
    [ctx] = seen
    assert ctx.model_grant is None


def test_a_harness_that_mints_no_grants_sends_none(tmp_path: Path) -> None:
    seen: list[RunContext] = []
    conductor = make_conductor(tmp_path, model_backed(seen))
    conductor.invoke(request("fake.none", record()), acting_for=TEST_PRINCIPAL)
    [ctx] = seen
    assert ctx.model_grant is None


def test_each_invocation_and_each_delegated_child_has_its_own_grant(
    keys: GrantKeys, tmp_path: Path
) -> None:
    parents: list[RunContext] = []
    children: list[RunContext] = []
    conductor = make_conductor(
        tmp_path,
        delegating_model_backed(parents, "fake.none", "fake.none"),
        model_backed(children),
        model_grants=keys.minter(),
    )

    env = conductor.invoke(request("fake.delegation", message()), acting_for=TEST_PRINCIPAL)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    grants = [ctx.model_grant for ctx in [*parents, *children]]
    assert all(grants) and len(set(grants)) == 3
    opened = [ModelGrantClaims.from_claims(keys.open(g).claims) for g in grants if g]
    assert [c.agent for c in opened] == ["fake.delegation", "fake.none", "fake.none"]
    child_ids = {d.delegated_invocation_id for d in env.delegations}
    assert {c.invocation for c in opened[1:]} == child_ids
    assert opened[0].invocation == env.invocation_id


def test_a_grant_a_caller_sends_is_never_passed_on(keys: GrantKeys, tmp_path: Path) -> None:
    seen: list[RunContext] = []
    # An agent that declares no model: the conductor mints it no grant, so whatever it is given
    # could only have come from the caller.
    conductor = make_conductor(tmp_path, model_backed(seen, models=()), model_grants=keys.minter())
    app = Starlette(routes=a2a_routes(conductor, OperatorAssertion(TEST_PRINCIPAL), HARNESS_URL)[1])
    forged = "eyJhbGciOiJub25lIn0.forged."

    task = send_to_harness(
        app, HARNESS_URL, request("fake.none", record()), metadata={META_MODEL_GRANT: forged}
    )

    assert task is not None
    [ctx] = seen
    assert ctx.model_grant is None


def test_the_grant_is_not_kept_in_any_record(keys: GrantKeys, tmp_path: Path) -> None:
    seen: list[RunContext] = []
    runs = tmp_path / "runs"
    conductor = make_conductor(runs, model_backed(seen), crate=True, model_grants=keys.minter())

    env = conductor.invoke(request("fake.none", record()), acting_for=TEST_PRINCIPAL)

    [ctx] = seen
    grant = ctx.model_grant
    assert grant
    stored = [p for p in runs.rglob("*") if p.is_file()]
    assert any(p.name == "ro-crate-metadata.json" for p in stored)
    for path in stored:
        assert grant.encode() not in path.read_bytes(), f"the grant is in {path}"
    assert grant not in json.dumps(to_document(env))


# --- The published keys ------------------------------------------------------------------------


def test_the_harness_publishes_its_public_keys_when_it_mints(keys: GrantKeys) -> None:
    app = Starlette(routes=jwks_routes(keys.minter()))
    response = TestClient(app).get(JWKS_PATH)
    assert response.status_code == 200
    assert response.json() == keys.minter().jwks()
    # A grant verifies against what was published, as the broker verifies it.
    grant = keys.minter().mint(
        agent_id="fake.none",
        invocation_id="inv-1",
        models=[MODEL],
        account=Account.DEPLOYMENT,
        acting_for=TEST_PRINCIPAL,
        lifetime_s=TIMEOUT_S,
    )
    assert keys.open(grant, response.json()).claims["dd_agent"] == "fake.none"


def test_a_harness_that_mints_nothing_publishes_nothing() -> None:
    assert jwks_routes(None) == []
