"""Environment-driven harness settings and the factory that assembles a Conductor.

Only harness concerns live here (where runs go, which institutional profile governs them, whom
the invocations act for, whether to write a crate, where the agent and source configurations
are). Agents are separate services and read their own `DD_<AGENT>_*` variables in their own
processes. Kept in one place so every way in (the workbench, the app, an A2A server) builds the
same object.

The configuration belongs to the deployment, not to the harness (ADR-0022): no path here has a
default inside a source tree. Each comes from its `DD_*` variable or from a default the caller
supplies, such as the workbench's development set in `workbench.config`.

`load_env_file` fills unset variables from a local `.env` file for development. Only a
console-script entry calls it; `Settings.from_env()` reads the real environment alone.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from dd_harness.conductor import Conductor
from dd_harness.identity import (
    Authenticator,
    BearerTokenAuthenticator,
    IdentityError,
    IssuerKeys,
    OidcProvider,
    OperatorAssertion,
)
from dd_harness.policy import load_profile
from dd_harness.registry import Registered, Registry
from dd_harness.sources import Sources
from dd_harness.store import RunStore
from dd_sdk.contract.models import Principal, PrincipalKind


class SettingsError(ValueError):
    """A required setting is unset, and the caller supplied no default for it."""


def load_env_file(path: Path, environ: MutableMapping[str, str] = os.environ) -> bool:
    """Fill unset variables from a local `.env` file; a variable already set is never replaced.

    A convenience for development: the real environment (a shell `export`, CI, a deployment)
    always wins. Returns whether the file exists; a missing file changes nothing.
    """
    if not path.is_file():
        return False
    for key, value in dotenv_values(path).items():
        if value is not None:
            environ.setdefault(key, value)
    return True


def _path(variable: str, default: Path | None) -> Path:
    """The path `variable` names, else the caller's default. With neither, start-up stops."""
    value = os.environ.get(variable)
    if value:
        return Path(value)
    if default is None:
        raise SettingsError(
            f"{variable} unset: the deployment names this file or directory (ADR-0022)"
        )
    return default


def projects_dir(default: Path | None = None) -> Path:
    """Where project records are kept: `DD_PROJECTS_DIR`, which has no default (ADR-0034)."""
    return _path("DD_PROJECTS_DIR", default)


def repositories_dir(default: Path | None = None) -> Path:
    """The deployment's requirement sets: `DD_REPOSITORIES_DIR`, which has no default (ADR-0038)."""
    return _path("DD_REPOSITORIES_DIR", default)


def named_principal(
    principal_id: str | None, principal_name: str | None, principal_kind: str
) -> Principal:
    """The principal the operator names. Raises `IdentityError` if it is unset or malformed."""
    missing = [
        var
        for var, value in (("DD_PRINCIPAL_ID", principal_id), ("DD_PRINCIPAL_NAME", principal_name))
        if not value
    ]
    if missing:
        raise IdentityError(
            f"{' and '.join(missing)} unset: every invocation acts for a named human "
            "(Blueprint §5.4, ADR-0018); see env.example"
        )
    try:
        return Principal(
            principal_id=str(principal_id),
            name=str(principal_name),
            principal_kind=PrincipalKind(principal_kind),
        )
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise IdentityError(f"the configured principal is malformed: {exc}") from exc


def principal_from_env() -> Principal:
    """The operator's principal from `DD_PRINCIPAL_*`, for a caller with no other settings."""
    return named_principal(
        os.environ.get("DD_PRINCIPAL_ID") or None,
        os.environ.get("DD_PRINCIPAL_NAME") or None,
        os.environ.get("DD_PRINCIPAL_KIND") or PrincipalKind.PERSON.value,
    )


@dataclass(frozen=True)
class Settings:
    runs_dir: Path
    # The one institutional profile this deployment applies to every invocation (ADR-0017).
    profile: Path
    agents_config: Path
    # The independent copies of sources the source check resolves evidence against (ADR-0016).
    sources_config: Path
    write_crate: bool = True
    # The address delegation agents call the harness back on (ADR-0012). `workbench serve`
    # uses its own host and port when this is unset; set it when agents reach the harness by
    # another name (a container network, a proxy).
    harness_url: str | None = None
    # The human every invocation acts for until there is authentication (ADR-0018). No default:
    # an agent must not operate anonymously, so an unset principal stops start-up.
    principal_id: str | None = None
    principal_name: str | None = None
    principal_kind: str = PrincipalKind.PERSON.value
    # The OpenID Connect provider whose ID tokens a caller sends as a bearer token (ADR-0029).
    # Set, it replaces the operator's principal for every HTTP caller.
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None

    def principal(self) -> Principal:
        """The configured principal. Raises `IdentityError` if it is unset or malformed."""
        return named_principal(self.principal_id, self.principal_name, self.principal_kind)

    @classmethod
    def from_env(
        cls,
        *,
        runs_dir: Path | None = None,
        profile: Path | None = None,
        agents_config: Path | None = None,
        sources_config: Path | None = None,
    ) -> Settings:
        """The settings the environment names. A `DD_*` variable wins over the caller's default
        for that path; a path with neither raises `SettingsError`."""
        return cls(
            runs_dir=_path("DD_RUNS_DIR", runs_dir),
            profile=_path("DD_PROFILE", profile),
            agents_config=_path("DD_AGENTS_CONFIG", agents_config),
            sources_config=_path("DD_SOURCES_CONFIG", sources_config),
            write_crate=os.environ.get("DD_WRITE_CRATE", "1") != "0",
            harness_url=os.environ.get("DD_HARNESS_URL") or None,
            principal_id=os.environ.get("DD_PRINCIPAL_ID") or None,
            principal_name=os.environ.get("DD_PRINCIPAL_NAME") or None,
            principal_kind=os.environ.get("DD_PRINCIPAL_KIND") or PrincipalKind.PERSON.value,
            oidc_issuer=os.environ.get("DD_OIDC_ISSUER") or None,
            oidc_client_id=os.environ.get("DD_OIDC_CLIENT_ID") or None,
        )


def build_registry(settings: Settings, agents: Iterable[Registered] = ()) -> Registry:
    """The agents `agents_config` lists, and beside them `agents`: agent objects the caller runs
    in its own process. The profile still decides which may run."""
    registry = Registry.from_config(settings.agents_config)
    for agent in agents:
        registry.add(agent)
    return registry


def build_conductor(settings: Settings, *, agents: Iterable[Registered] = ()) -> Conductor:
    return Conductor(
        registry=build_registry(settings, agents),
        store=RunStore(settings.runs_dir),
        profile=load_profile(settings.profile),  # a bad profile stops start-up, not a request
        write_crate=settings.write_crate,
        sources=Sources.from_config(settings.sources_config),
    )


def build_authenticator(settings: Settings) -> Authenticator:
    """The bearer-token authenticator if a provider is configured (ADR-0029), else the stub
    (ADR-0018). A provider configured beside an operator principal, a provider without a client
    ID, or neither provider nor principal stops start-up, not a request."""
    if settings.oidc_issuer is None:
        return OperatorAssertion(settings.principal())
    if settings.principal_id or settings.principal_name:
        raise IdentityError(
            "DD_OIDC_ISSUER and DD_PRINCIPAL_ID are both set: a server that signs people in "
            "never gives a caller the operator's principal (ADR-0029); unset one"
        )
    if not settings.oidc_client_id:
        raise IdentityError("DD_OIDC_CLIENT_ID unset: DD_OIDC_ISSUER needs the client ID")
    provider = OidcProvider(issuer=settings.oidc_issuer, client_id=settings.oidc_client_id)
    return BearerTokenAuthenticator(provider, IssuerKeys(provider.issuer))
