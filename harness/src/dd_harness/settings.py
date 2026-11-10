"""Environment-driven harness settings and the factory that assembles a Conductor.

Only harness concerns live here (where runs go, which institutional profile governs them, whom
the invocations act for, whether to write a crate, where the agent and source configurations
are). Agents are separate services and read their own `DD_<AGENT>_*` variables in their own
processes. Kept in one place so every way in (the workbench, the app, an A2A server) builds the
same object.

The configuration belongs to the deployment, not to the harness (docs/specs/system.md): no path here
has a default inside a source tree. Each comes from its `DD_*` variable or from a default the caller
supplies, such as the workbench's development set in `workbench.config`.

`load_env_file` fills unset variables from a local `.env` file for development. Only a
console-script entry calls it; `Settings.from_env()` reads the real environment alone.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qsl, urlsplit
from urllib.request import url2pathname

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
from dd_harness.projects import Projects, ProjectStore
from dd_harness.registry import Registered, Registry
from dd_harness.sources import Sources
from dd_harness.storage import ProjectStorage, RunStorage
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
            f"{variable} unset: the deployment names this file or directory (docs/specs/system.md)"
        )
    return default


# The schemes a storage location may name in this build (docs/specs/storage.md). A location with no
# scheme is a path; it and `file://` mean the file backends, and `postgresql://` the PostgreSQL one.
STORAGE_SCHEMES = ("file", "postgresql")
POSTGRES = "postgresql"

# Where runs or projects are kept: a directory for the file backends, or a `postgresql://` URL.
type StorageLocation = Path | str


def storage_location(
    location: StorageLocation, variable: str = "a storage location"
) -> StorageLocation:
    """What a storage location names: the directory a path or a `file://` URL names, or a
    `postgresql://` URL as given. Raises `SettingsError` for any other scheme, naming the ones this
    build supports, and for a database URL that carries a credential (invariant 13)."""
    if isinstance(location, Path) or "://" not in location:
        return Path(location)
    parsed = urlsplit(location)
    if parsed.scheme not in STORAGE_SCHEMES:
        supported = ", ".join(f"{s}://" for s in STORAGE_SCHEMES)
        raise SettingsError(
            f"{variable}: {parsed.scheme}:// storage is not supported by this build; "
            f"name a path or one of {supported} (docs/specs/storage.md)"
        )
    if parsed.scheme == POSTGRES:
        query = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
        if parsed.password is not None or "password" in query:
            raise SettingsError(
                f"{variable}: {redact_location(location)} carries a password; a location never "
                "does: give it in libpq's password file, service file or PGPASSWORD "
                "(docs/specs/storage.md)"
            )
        return location
    if parsed.netloc not in ("", "localhost"):
        raise SettingsError(f"{variable}: a file:// URL names no host, not {parsed.netloc!r}")
    return Path(url2pathname(parsed.path))


def redact_location(location: StorageLocation) -> str:
    """A storage location as a person may be shown it: a database URL without its user, password
    or parameters (docs/specs/storage.md, invariant 13)."""
    if isinstance(location, Path) or "://" not in location:
        return str(location)
    parsed = urlsplit(location)
    host = parsed.hostname or ""
    if ":" in host:  # an IPv6 address
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port is not None else host
    # Written out, not with urlunsplit, which drops the `//` of a URL that names no host.
    return f"{parsed.scheme}://{netloc}{parsed.path}"


def _storage(variable: str, default: Path | None) -> StorageLocation:
    """The storage location `variable` names, else the caller's default."""
    value = os.environ.get(variable)
    return storage_location(value, variable) if value else _path(variable, default)


def _postgres(variable: str) -> ModuleType:
    """The PostgreSQL backend, imported only when a location names it, so a deployment on files
    does not install its driver."""
    try:
        return importlib.import_module("dd_harness.postgres")
    except ImportError as exc:
        raise SettingsError(
            f"{variable}: postgresql:// storage needs its driver; install "
            "data-director-harness[postgres] (docs/specs/storage.md)"
        ) from exc


POOL_SIZE_VARIABLE = "DD_POSTGRES_POOL_SIZE"


def postgres_pool_size() -> int | None:
    """The most connections one PostgreSQL store keeps: `DD_POSTGRES_POOL_SIZE`, or None for the
    backend's default (docs/specs/storage.md). Anything but a positive whole number stops start-up
    with `SettingsError`."""
    value = os.environ.get(POOL_SIZE_VARIABLE, "").strip()
    if not value:
        return None
    if not value.isdecimal() or int(value) < 1:
        raise SettingsError(
            f"{POOL_SIZE_VARIABLE}={value!r}: the pool size is a whole number of connections, "
            "at least 1 (docs/specs/storage.md)"
        )
    return int(value)


def _pooled() -> dict[str, int]:
    """The pool size to pass a PostgreSQL store, if the environment names one."""
    size = postgres_pool_size()
    return {} if size is None else {"pool_size": size}


def run_storage(location: StorageLocation, variable: str = "DD_RUNS_DIR") -> RunStorage:
    """The run storage at `location` (`DD_RUNS_DIR`): a path or `file://` URL is the file backend,
    a `postgresql://` URL the PostgreSQL one (docs/specs/storage.md). A location that cannot be
    used stops start-up with `SettingsError`."""
    where = storage_location(location, variable)
    if isinstance(where, Path):
        return _on_files(variable, where, RunStore)
    pooled = _pooled()
    try:
        store: RunStorage = _postgres(variable).PostgresRunStore(where, **pooled)
    except SettingsError as exc:
        raise SettingsError(f"{variable} {exc}") from exc
    return store


def project_storage(location: StorageLocation, variable: str = "DD_PROJECTS_DIR") -> ProjectStorage:
    """The project storage at `location` (`DD_PROJECTS_DIR`): the project rules over the file log
    for a path or `file://` URL, or over the PostgreSQL log for a `postgresql://` URL
    (docs/specs/storage.md). A location that cannot be used stops start-up with `SettingsError`."""
    where = storage_location(location, variable)
    if isinstance(where, Path):
        return _on_files(variable, where, ProjectStore)
    pooled = _pooled()
    try:
        log = _postgres(variable).PostgresProjectLog(where, **pooled)
    except SettingsError as exc:
        raise SettingsError(f"{variable} {exc}") from exc
    return Projects(log)


def _on_files[S](variable: str, root: Path, backend: Callable[[Path], S]) -> S:
    try:
        return backend(root)
    except OSError as exc:
        # One line at start-up, like any other setting that is wrong.
        raise SettingsError(f"{variable} {root} cannot be used: {exc.strerror or exc}") from exc


def projects_dir(default: Path | None = None) -> StorageLocation:
    """Where project records are kept: `DD_PROJECTS_DIR`, which has no default
    (docs/specs/projects.md)."""
    return _storage("DD_PROJECTS_DIR", default)


def runs_dir(default: Path | None = None) -> StorageLocation:
    """Where runs are kept: `DD_RUNS_DIR`, which has no default (docs/specs/storage.md)."""
    return _storage("DD_RUNS_DIR", default)


def repositories_dir(default: Path | None = None) -> Path:
    """The deployment's requirement sets: `DD_REPOSITORIES_DIR`, which has no default
    (docs/specs/deposit.md)."""
    return _path("DD_REPOSITORIES_DIR", default)


def sources_config(default: Path | None = None) -> Path:
    """The deployment's `sources.yaml`: `DD_SOURCES_CONFIG`, which has no default
    (harness/src/dd_harness/sources.py)."""
    return _path("DD_SOURCES_CONFIG", default)


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
            "(Blueprint §5.4, docs/specs/policy-and-identity.md); see env.example"
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
    # A directory, or a `postgresql://` URL (docs/specs/storage.md).
    runs_dir: StorageLocation
    # The one institutional profile this deployment applies to every invocation
    # (docs/specs/policy-and-identity.md).
    profile: Path
    agents_config: Path
    # The independent copies of sources the source check resolves evidence against
    # (docs/specs/grounding.md).
    sources_config: Path
    write_crate: bool = True
    # The address delegation agents call the harness back on (docs/specs/orchestration.md).
    # `workbench serve` uses its own host and port when this is unset; set it when agents reach the
    # harness by another name (a container network, a proxy).
    harness_url: str | None = None
    # The human every invocation acts for until there is authentication
    # (docs/specs/policy-and-identity.md). No default: an agent must not operate anonymously, so an
    # unset principal stops start-up.
    principal_id: str | None = None
    principal_name: str | None = None
    principal_kind: str = PrincipalKind.PERSON.value
    # The OpenID Connect provider whose ID tokens a caller sends as a bearer token
    # (docs/specs/policy-and-identity.md). Set, it replaces the operator's principal for every HTTP
    # caller.
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
            runs_dir=_storage("DD_RUNS_DIR", runs_dir),
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
        store=run_storage(settings.runs_dir, "DD_RUNS_DIR"),
        profile=load_profile(settings.profile),  # a bad profile stops start-up, not a request
        write_crate=settings.write_crate,
        sources=Sources.from_config(settings.sources_config),
    )


def build_authenticator(settings: Settings) -> Authenticator:
    """The bearer-token authenticator if a provider is configured
    (docs/specs/policy-and-identity.md), else the stub. A
    provider configured beside an operator principal, a provider without a client ID, or neither
    provider nor principal stops start-up, not a request."""
    if settings.oidc_issuer is None:
        return OperatorAssertion(settings.principal())
    if settings.principal_id or settings.principal_name:
        raise IdentityError(
            "DD_OIDC_ISSUER and DD_PRINCIPAL_ID are both set: a server that signs people in "
            "never gives a caller the operator's principal (docs/specs/policy-and-identity.md); "
            "unset one"
        )
    if not settings.oidc_client_id:
        raise IdentityError("DD_OIDC_CLIENT_ID unset: DD_OIDC_ISSUER needs the client ID")
    provider = OidcProvider(issuer=settings.oidc_issuer, client_id=settings.oidc_client_id)
    return BearerTokenAuthenticator(provider, IssuerKeys(provider.issuer))
