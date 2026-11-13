"""The model grant's claims have one shape that the harness, the broker and an agent's adapter
share (docs/specs/model-accounts.md, The grant)."""

from __future__ import annotations

from typing import Any

import pytest

from dd_sdk import wire
from dd_sdk.model_grant import (
    BROKER_AUDIENCE,
    META_MODEL_GRANT,
    TICKET_PURPOSE,
    Account,
    EnrolmentTicketClaims,
    ModelGrantClaims,
    ModelGrantError,
    origin,
)


def claims(**change: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "aud": BROKER_AUDIENCE,
        "iat": 1_800_000_000,
        "exp": 1_800_000_300,
        "dd_agent": "advisor.standards",
        "dd_invocation": "inv-1",
        "dd_models": ["claude-sonnet-5-5"],
        "dd_account": "own-or-deployment",
        "dd_subject": "eyJ.sealed",
        "dd_providers": ["anthropic"],
        "dd_base_urls": ["https://models.example.ac.uk"],
    }
    return {k: v for k, v in (base | change).items() if v is not None}


def test_a_well_formed_claim_set_is_read() -> None:
    grant = ModelGrantClaims.from_claims(claims())
    assert grant.account is Account.OWN_OR_DEPLOYMENT
    assert grant.models == ("claude-sonnet-5-5",)
    assert grant.providers == ("anthropic",)
    assert grant.base_urls == ("https://models.example.ac.uk",)


def test_a_deployment_grant_names_no_own_account() -> None:
    grant = ModelGrantClaims.from_claims(
        claims(dd_account="deployment", dd_providers=None, dd_base_urls=None)
    )
    assert grant.providers == () and grant.base_urls == ()


@pytest.mark.parametrize(
    "change",
    [
        {"dd_account": "deployment"},
        {"dd_account": "deployment", "dd_providers": None},
        {"dd_providers": None},
        {"dd_providers": []},
        {"dd_providers": "anthropic"},
        {"dd_base_urls": [""]},
    ],
)
def test_own_account_claims_are_checked(change: dict[str, Any]) -> None:
    with pytest.raises(ModelGrantError):
        ModelGrantClaims.from_claims(claims(**change))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Models.Example.ac.uk/v1", "https://models.example.ac.uk"),
        ("https://models.example.ac.uk:443", "https://models.example.ac.uk"),
        ("https://models.example.ac.uk:8443/", "https://models.example.ac.uk:8443"),
    ],
)
def test_an_origin_is_written_one_way(url: str, expected: str) -> None:
    assert origin(url) == expected


@pytest.mark.parametrize(
    "url", ["http://models.example.ac.uk", "https://u:p@models.example.ac.uk", "https://x/?q=1"]
)
def test_an_origin_is_only_a_plain_https_url(url: str) -> None:
    with pytest.raises(ValueError):
        origin(url)


@pytest.mark.parametrize(
    "change",
    [
        {"dd_agent": None},
        {"dd_agent": ""},
        {"dd_models": []},
        {"dd_models": "claude-sonnet-5-5"},
        {"dd_models": [1]},
        {"dd_account": "theirs"},
        {"dd_subject": None},
        {"iat": "now"},
        {"exp": True},
        {"exp": 1_799_999_999},
    ],
)
def test_a_malformed_claim_set_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ModelGrantError):
        ModelGrantClaims.from_claims(claims(**change))


def test_the_wire_names_the_grant_beside_the_other_metadata() -> None:
    assert wire.META_MODEL_GRANT == META_MODEL_GRANT
    assert META_MODEL_GRANT.startswith("dd.")


def ticket_claims(**change: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "aud": BROKER_AUDIENCE,
        "iat": 1_800_000_000,
        "exp": 1_800_000_120,
        "jti": "t-1",
        "dd_purpose": TICKET_PURPOSE,
        "dd_subject": "eyJ.sealed",
    }
    return {k: v for k, v in (base | change).items() if v is not None}


def test_a_well_formed_ticket_is_read() -> None:
    ticket = EnrolmentTicketClaims.from_claims(ticket_claims())
    assert ticket.ticket_id == "t-1"
    assert ticket.subject == "eyJ.sealed"


@pytest.mark.parametrize(
    "change",
    [
        {"jti": None},
        {"dd_purpose": None},
        {"dd_purpose": "grant"},
        {"dd_subject": None},
        {"exp": 1_799_999_999},
        {"dd_agent": "advisor.standards"},
        {"dd_models": ["claude-sonnet-5-5"]},
    ],
)
def test_a_malformed_ticket_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ModelGrantError):
        EnrolmentTicketClaims.from_claims(ticket_claims(**change))


def test_a_grant_is_not_a_ticket_and_a_ticket_is_not_a_grant() -> None:
    with pytest.raises(ModelGrantError):
        EnrolmentTicketClaims.from_claims(claims())
    with pytest.raises(ModelGrantError):
        ModelGrantClaims.from_claims(claims() | {"dd_purpose": TICKET_PURPOSE})
