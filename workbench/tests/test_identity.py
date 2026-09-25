"""Whom an invocation acts for (ADR-0018): the configured principal, and the refusal to start
without one."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from dd_sdk.contract.models import Assurance, PrincipalKind
from workbench import cli
from workbench.identity import IdentityError, OperatorAssertion
from workbench.settings import Settings, build_authenticator
from workbench.testing import TEST_PRINCIPAL

ORCID = TEST_PRINCIPAL.principal_id
UNSET = ("DD_PRINCIPAL_ID", "DD_PRINCIPAL_NAME", "DD_PRINCIPAL_KIND")


@pytest.fixture
def no_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in UNSET:
        monkeypatch.delenv(variable, raising=False)


@pytest.mark.requirement("DD-ACTS-FOR")
def test_an_unset_principal_stops_start_up(no_principal: None) -> None:
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME unset"):
        build_authenticator(Settings.from_env())
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_NAME unset"):
        Settings(principal_id=ORCID).principal()


@pytest.mark.requirement("DD-ACTS-FOR")
@pytest.mark.parametrize(
    "command", [["invoke", "--agent", "hello.world", "--input", "samples/claim.json"], ["serve"]]
)
def test_the_cli_runs_nothing_without_a_principal(
    no_principal: None, command: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path))
    with pytest.raises(SystemExit, match="DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME unset"):
        cli.main(command)
    assert list(tmp_path.iterdir()) == []


def test_a_malformed_principal_is_a_configuration_error() -> None:
    with pytest.raises(IdentityError, match="malformed"):
        Settings(principal_id="0000-0002-1825-0097", principal_name="J. Carberry").principal()
    with pytest.raises(IdentityError, match="malformed"):
        Settings(principal_id=ORCID, principal_name="J", principal_kind="robot").principal()


@pytest.mark.requirement("DD-ACTS-FOR")
def test_the_stub_asserts_the_configured_principal_whoever_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DD_PRINCIPAL_ID", "urn:example:role:data-steward")
    monkeypatch.setenv("DD_PRINCIPAL_NAME", "Data steward")
    monkeypatch.setenv("DD_PRINCIPAL_KIND", "accountable_role")
    authenticator = build_authenticator(Settings.from_env())
    assert isinstance(authenticator, OperatorAssertion)
    named = authenticator.principal_for(None)
    assert named.principal_kind == PrincipalKind.ACCOUNTABLE_ROLE
    assert named.assurance == Assurance.ASSERTED
    # A header naming someone else changes nothing: the stub authenticates no one.
    assert authenticator.principal_for({"authorization": "Bearer someone-else"}) == named


def test_the_cli_flags_replace_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_PRINCIPAL_ID", "urn:example:someone")
    monkeypatch.setenv("DD_PRINCIPAL_NAME", "Someone")
    args = argparse.Namespace(
        profile=None, acting_for_id=ORCID, acting_for_name=TEST_PRINCIPAL.name
    )
    assert cli._settings(args).principal() == TEST_PRINCIPAL
