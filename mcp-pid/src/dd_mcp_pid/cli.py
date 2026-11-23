"""`dd-mcp-pid serve`: run the server (README.md).

Settings, from the environment:

- `DD_PID_ROR`: `dump` (the default) reads ROR from the built registry and asks ROR's API only
  when the registry cannot be read; `live` asks the API only.
- `DD_PID_ROR_REGISTRY`: the built registry (`registry.jsonl`). In the Data Director it is the
  policy advisor's, built by `uv run dd-sources prepare`.
- `DD_PID_ROR_SNAPSHOT`: which dump the registry was built from, as said in answers (such as
  `ROR dump v2.15`).
- `DD_PID_JOURNALS_REGISTRY`: the journal registry's index (`journals.sqlite`), built by
  `dd-journals fetch` (in the Data Director, `uv run dd-sources prepare`). Unset: where
  `dd-journals` builds it.
- `DD_PID_HOSTS`: comma-separated names clients reach the server by, beyond loopback (such as a
  container's service name).
- `DD_REGISTRY_CONTACT`: the operators' contact address, which DataCite and Crossref are sent as
  `mailto:` in the User-Agent so that they serve the server from their faster, identified pool.
  Never a person's own address. Unset, no address is sent. OpenAIRE is sent it as `mailto`, which
  its API takes for its polite pool.
- `DD_OPENAIRE_REFRESH_TOKEN`: a secret, an OpenAIRE refresh token. Each request to the OpenAIRE
  Graph then carries an access token issued from it, which raises the limit from 60 requests an
  hour to 7,200. A refresh token lasts a month. Unset, OpenAIRE is asked anonymously.
- `DD_PID_CACHE_DIR`: the directory for the cache of the registries' answers (`pid.sqlite3`).
  Unset, the cache is kept in memory for the life of the process.
- `DD_PID_CACHE_TTL_FOUND`, `DD_PID_CACHE_TTL_MISSING`: how many seconds a found record and a
  "no such identifier" answer are used without asking again.
- `DD_PID_OFFLINE`: `1` asks no registry: ROR is read from the built registry, everything else
  from the cache, and an identifier in neither is unavailable.
- `DD_PID_ROR_CLIENT_ID_FILE`: a file holding ROR's client ID, sent as `Client-Id`; a relative
  path is under `$CREDENTIALS_DIRECTORY`. Unset, ROR is asked anonymously.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import uvicorn

from dd_journals.snapshot import INDEX
from dd_mcp_pid.app import LOOPBACK, create_app
from dd_mcp_pid.caching import DEFAULT_TTL, Lookups, lookups
from dd_mcp_pid.dois import Crossref, DataCite
from dd_mcp_pid.grant_server import GrantSources, grant_registry
from dd_mcp_pid.grants import AccessToken, CrossrefGrants, OpenAireGraph
from dd_mcp_pid.http import contact_address
from dd_mcp_pid.journals import JournalSource, journal_registry
from dd_mcp_pid.orcid import Orcid
from dd_mcp_pid.ror import RorApi, RorIndex
from dd_mcp_pid.tools import (
    Registry,
    RorSources,
    doi_registry,
    orcid_registry,
    ror_registry,
)
from dd_registry_cache import Ttl

DEFAULT_PORT = 8310


class SettingsError(Exception):
    """A setting has a value the server cannot use. The message names it."""


def ror_client_id(env: Mapping[str, str]) -> str | None:
    """ROR's client ID, read from the file `DD_PID_ROR_CLIENT_ID_FILE`, or None when unset."""
    name = "DD_PID_ROR_CLIENT_ID_FILE"
    file = env.get(name, "").strip()
    if not file:
        return None
    path = Path(file)
    if not path.is_absolute():
        directory = env.get("CREDENTIALS_DIRECTORY", "").strip()
        if not directory:
            raise SettingsError(f"{name}={file} is relative and CREDENTIALS_DIRECTORY is not set")
        path = Path(directory) / path
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SettingsError(f"{name}: cannot read {path}: {exc.strerror}") from None
    if not value or any(c.isspace() for c in value):
        raise SettingsError(f"{name}: {path} does not hold one client ID")
    return value


def offline(env: Mapping[str, str]) -> bool:
    value = env.get("DD_PID_OFFLINE", "").strip()
    if value not in {"", "0", "1"}:
        raise SettingsError(f"DD_PID_OFFLINE must be 0 or 1, not {value!r}")
    return value == "1"


def _seconds(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise SettingsError(f"{name} must be a number of seconds, not {raw!r}") from None
    if not value >= 0:
        raise SettingsError(f"{name} must not be negative")
    return value


def cache(env: Mapping[str, str]) -> Lookups:
    directory = env.get("DD_PID_CACHE_DIR", "").strip()
    ttl = Ttl(
        found=_seconds(env, "DD_PID_CACHE_TTL_FOUND", DEFAULT_TTL.found),
        missing=_seconds(env, "DD_PID_CACHE_TTL_MISSING", DEFAULT_TTL.missing),
    )
    return lookups(Path(directory) if directory else None, ttl, offline=offline(env))


def ror_sources(env: Mapping[str, str], cached: Lookups) -> RorSources:
    mode = env.get("DD_PID_ROR", "dump").strip().lower() or "dump"
    if mode not in {"dump", "live"}:
        raise SettingsError(f"DD_PID_ROR must be dump or live, not {mode!r}")
    if mode == "live" and cached.offline:
        raise SettingsError("DD_PID_ROR=live asks ROR's API, which DD_PID_OFFLINE=1 forbids")
    api = None if cached.offline else RorApi(client_id=ror_client_id(env))
    if mode == "live":
        return RorSources(index=None, api=api, lookups=cached)
    registry = env.get("DD_PID_ROR_REGISTRY", "").strip()
    index = RorIndex(Path(registry)) if registry else None
    label = env.get("DD_PID_ROR_SNAPSHOT", "").strip() or "ROR dump"
    return RorSources(index=index, api=api, index_label=label, lookups=cached)


def contact(env: Mapping[str, str]) -> str | None:
    try:
        return contact_address(env.get("DD_REGISTRY_CONTACT", ""))
    except ValueError as exc:
        raise SettingsError(f"DD_REGISTRY_CONTACT: {exc}") from None


def journal_source(env: Mapping[str, str]) -> JournalSource:
    index = env.get("DD_PID_JOURNALS_REGISTRY", "").strip()
    return JournalSource(Path(index) if index else INDEX)


def grant_sources(env: Mapping[str, str], address: str | None, cached: Lookups) -> GrantSources:
    refresh = env.get("DD_OPENAIRE_REFRESH_TOKEN", "").strip()
    token = AccessToken(refresh) if refresh else None
    return GrantSources(
        CrossrefGrants(contact=address),
        OpenAireGraph(contact=address, token=token),
        offline=cached.offline,
    )


def registries(env: Mapping[str, str]) -> list[Registry]:
    address = contact(env)
    cached = cache(env)
    return [
        doi_registry("DataCite", DataCite(contact=address), cached),
        doi_registry("Crossref", Crossref(contact=address), cached),
        orcid_registry(Orcid(), cached),
        ror_registry(ror_sources(env, cached)),
        journal_registry(journal_source(env)),
        grant_registry(grant_sources(env, address, cached)),
    ]


def hosts(env: Mapping[str, str]) -> list[str]:
    extra = [h.strip() for h in env.get("DD_PID_HOSTS", "").split(",") if h.strip()]
    return [*LOOPBACK, *extra]


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-mcp-pid`."""
    parser = argparse.ArgumentParser(prog="dd-mcp-pid", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the registries' MCP servers over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    try:
        app = create_app(registries(os.environ), hosts(os.environ))
    except SettingsError as exc:
        parser.error(str(exc))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
