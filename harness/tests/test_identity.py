"""Whom an invocation acts for (ADR-0018): the configured principal, and the refusal to start
without one."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from dd_harness.identity import IdentityError, OperatorAssertion
from dd_harness.settings import Settings, build_authenticator
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL
from dd_sdk.contract.models import Assurance, PrincipalKind

ORCID = TEST_PRINCIPAL.principal_id
UNSET = ("DD_PRINCIPAL_ID", "DD_PRINCIPAL_NAME", "DD_PRINCIPAL_KIND")


def env_settings() -> Settings:
    """The environment's settings, with the test profile and placeholder paths for the rest; no
    test here reads any of the files."""
    return Settings.from_env(
        runs_dir=Path("runs"),
        profile=PERMISSIVE,
        agents_config=Path("agents.yaml"),
        sources_config=Path("sources.yaml"),
    )


def principal_settings(
    principal_id: str | None, name: str | None = None, kind: str = "person"
) -> Settings:
    """Settings with exactly this principal, whatever the environment says."""
    return replace(
        env_settings(), principal_id=principal_id, principal_name=name, principal_kind=kind
    )


@pytest.fixture
def no_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in UNSET:
        monkeypatch.delenv(variable, raising=False)


@pytest.mark.requirement("DD-ACTS-FOR")
def test_an_unset_principal_stops_start_up(no_principal: None) -> None:
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME unset"):
        build_authenticator(env_settings())
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_NAME unset"):
        principal_settings(ORCID).principal()


def test_a_malformed_principal_is_a_configuration_error() -> None:
    with pytest.raises(IdentityError, match="malformed"):
        principal_settings("0000-0002-1825-0097", "J. Carberry").principal()
    with pytest.raises(IdentityError, match="malformed"):
        principal_settings(ORCID, "J", "robot").principal()


@pytest.mark.requirement("DD-ACTS-FOR")
def test_the_stub_asserts_the_configured_principal_whoever_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DD_PRINCIPAL_ID", "urn:example:role:data-steward")
    monkeypatch.setenv("DD_PRINCIPAL_NAME", "Data steward")
    monkeypatch.setenv("DD_PRINCIPAL_KIND", "accountable_role")
    authenticator = build_authenticator(env_settings())
    assert isinstance(authenticator, OperatorAssertion)
    named = authenticator.principal_for(None)
    assert named.principal_kind == PrincipalKind.ACCOUNTABLE_ROLE
    assert named.assurance == Assurance.ASSERTED
    # A header naming someone else changes nothing: the stub authenticates no one.
    assert authenticator.principal_for({"authorization": "Bearer someone-else"}) == named
