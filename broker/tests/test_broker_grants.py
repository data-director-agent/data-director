"""The broker accepts a grant only if the harness signed it for the broker and the calling agent,
and it has not expired (docs/specs/model-accounts.md, invariants 4 and 7)."""

from __future__ import annotations

import time

import pytest
from broker_support import AGENT, MODEL, OTHER_AGENT, PSEUDONYM, FakeHarness
from joserfc.jwk import ECKey, RSAKey

from dd_broker.grants import GrantVerifier, subject_key
from dd_broker.reasons import Refused
from dd_sdk.model_grant import Account


def refusal(verifier: GrantVerifier, token: str | None, agent: str = AGENT) -> str:
    with pytest.raises(Refused) as caught:
        verifier.verify(token, agent)
    return caught.value.reason.value


def test_a_valid_grant_names_the_pseudonym_and_the_models() -> None:
    harness = FakeHarness()
    grant = harness.verifier().verify(harness.grant(account=Account.OWN_OR_DEPLOYMENT), AGENT)

    assert grant.pseudonym == PSEUDONYM
    assert grant.claims.account is Account.OWN_OR_DEPLOYMENT
    assert grant.allows(MODEL)
    assert not grant.allows("claude-opus-5-5")
    assert PSEUDONYM not in repr(grant)


def test_the_pseudonym_is_sealed_and_differs_in_every_grant() -> None:
    harness = FakeHarness()
    first, second = harness.claims(), harness.claims()
    assert first["dd_subject"] != second["dd_subject"]
    assert PSEUDONYM not in first["dd_subject"]


def test_a_grant_signed_by_another_key_is_refused() -> None:
    harness = FakeHarness()
    impostor = RSAKey.generate_key(2048, parameters={"kid": "harness-1", "alg": "RS256"})
    assert refusal(harness.verifier(), harness.sign(harness.claims(), impostor)) == "grant-invalid"


def test_a_grant_for_another_audience_is_refused() -> None:
    harness = FakeHarness()
    claims = harness.claims() | {"aud": "urn:somewhere-else"}
    assert refusal(harness.verifier(), harness.sign(claims)) == "grant-invalid"


def test_an_expired_grant_is_refused() -> None:
    harness = FakeHarness()
    stale = harness.grant(issued_at=int(time.time()) - 3600, lifetime=60)
    assert refusal(harness.verifier(), stale) == "grant-expired"


def test_a_grant_presented_by_another_agent_is_refused() -> None:
    harness = FakeHarness()
    assert refusal(harness.verifier(), harness.grant(), OTHER_AGENT) == "grant-agent-mismatch"


@pytest.mark.parametrize(
    "change",
    [
        {"dd_models": []},
        {"dd_account": "someone-else"},
        {"dd_subject": "not-a-jwe"},
        {"dd_agent": None},
    ],
)
def test_a_grant_of_the_wrong_shape_is_refused(change: dict[str, object]) -> None:
    harness = FakeHarness()
    claims = {k: v for k, v in (harness.claims() | change).items() if v is not None}
    assert refusal(harness.verifier(), harness.sign(claims)) == "grant-invalid"


def test_a_subject_sealed_to_another_broker_is_refused() -> None:
    harness, other = FakeHarness(), FakeHarness()
    claims = harness.claims() | {"dd_subject": other.seal_subject()}
    assert refusal(harness.verifier(), harness.sign(claims)) == "grant-invalid"


def test_an_unsigned_grant_is_refused() -> None:
    harness = FakeHarness()
    _, payload, _ = harness.grant().split(".")
    unsigned = f"eyJhbGciOiJub25lIn0.{payload}."
    assert refusal(harness.verifier(), unsigned) == "grant-invalid"
    assert refusal(harness.verifier(), None) == "grant-missing"


def test_a_rotated_harness_key_is_fetched_once() -> None:
    harness = FakeHarness()
    clock = [1000.0]
    verifier = GrantVerifier(harness.keys(clock=lambda: clock[0]), harness.subject_key)
    verifier.verify(harness.grant(), AGENT)
    assert harness.fetches == 1

    harness.signing_key = RSAKey.generate_key(
        2048, parameters={"kid": "harness-2", "alg": "RS256", "use": "sig"}
    )
    clock[0] += 120
    verifier.verify(harness.grant(), AGENT)
    verifier.verify(harness.grant(), AGENT)
    assert harness.fetches == 2


def test_a_run_of_unknown_keys_does_not_become_a_run_of_fetches() -> None:
    harness = FakeHarness()
    verifier = harness.verifier()
    verifier.verify(harness.grant(), AGENT)
    stranger = RSAKey.generate_key(2048, parameters={"kid": "unknown", "alg": "RS256"})
    for _ in range(3):
        refusal(verifier, harness.sign(harness.claims(), stranger))
    assert harness.fetches == 1


def test_the_subject_key_must_be_a_private_p256_key() -> None:
    key = ECKey.generate_key("P-256")
    assert subject_key(key.as_pem(private=True).decode()).is_private
    for wrong in (
        key.as_pem(private=False).decode(),
        ECKey.generate_key("P-384").as_pem(private=True).decode(),
        "not a key",
    ):
        with pytest.raises(ValueError):
            subject_key(wrong)
