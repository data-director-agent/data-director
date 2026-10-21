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
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from dd_harness.conductor import Conductor
from dd_harness.identity import Authenticator, IdentityError, OperatorAssertion
from dd_harness.policy import load_profile
from dd_harness.registry import Registry
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
    workbench_url: str | None = None
    # The human every invocation acts for until there is authentication (ADR-0018). No default:
    # an agent must not operate anonymously, so an unset principal stops start-up.
    principal_id: str | None = None
    principal_name: str | None = None
    principal_kind: str = PrincipalKind.PERSON.value

    def principal(self) -> Principal:
        """The configured principal. Raises `IdentityError` if it is unset or malformed."""
        missing = [
            var
            for var, value in (
                ("DD_PRINCIPAL_ID", self.principal_id),
                ("DD_PRINCIPAL_NAME", self.principal_name),
            )
            if not value
        ]
        if missing:
            raise IdentityError(
                f"{' and '.join(missing)} unset: every invocation acts for a named human "
                "(Blueprint §5.4, ADR-0018); see env.example"
            )
        try:
            return Principal(
                principal_id=str(self.principal_id),
                name=str(self.principal_name),
                principal_kind=PrincipalKind(self.principal_kind),
            )
        except ValueError as exc:  # pydantic's ValidationError is a ValueError
            raise IdentityError(f"the configured principal is malformed: {exc}") from exc

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
            workbench_url=os.environ.get("DD_WORKBENCH_URL") or None,
            principal_id=os.environ.get("DD_PRINCIPAL_ID") or None,
            principal_name=os.environ.get("DD_PRINCIPAL_NAME") or None,
            principal_kind=os.environ.get("DD_PRINCIPAL_KIND") or PrincipalKind.PERSON.value,
        )


def build_registry(settings: Settings) -> Registry:
    return Registry.from_config(settings.agents_config)


def build_conductor(settings: Settings) -> Conductor:
    return Conductor(
        registry=build_registry(settings),
        store=RunStore(settings.runs_dir),
        profile=load_profile(settings.profile),  # a bad profile stops start-up, not a request
        write_crate=settings.write_crate,
        sources=Sources.from_config(settings.sources_config),
    )


def build_authenticator(settings: Settings) -> Authenticator:
    """The stub authenticator (ADR-0018). An unset principal stops start-up, not a request."""
    return OperatorAssertion(settings.principal())
