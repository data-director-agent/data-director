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
  Never a person's own address. Unset, no address is sent.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import uvicorn

from dd_journals.snapshot import INDEX
from dd_mcp_pid.app import LOOPBACK, create_app
from dd_mcp_pid.dois import Crossref, DataCite
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

DEFAULT_PORT = 8310


class SettingsError(Exception):
    """A setting has a value the server cannot use. The message names it."""


def ror_sources(env: Mapping[str, str]) -> RorSources:
    mode = env.get("DD_PID_ROR", "dump").strip().lower() or "dump"
    if mode == "live":
        return RorSources(index=None, api=RorApi())
    if mode != "dump":
        raise SettingsError(f"DD_PID_ROR must be dump or live, not {mode!r}")
    registry = env.get("DD_PID_ROR_REGISTRY", "").strip()
    index = RorIndex(Path(registry)) if registry else None
    label = env.get("DD_PID_ROR_SNAPSHOT", "").strip() or "ROR dump"
    return RorSources(index=index, api=RorApi(), index_label=label)


def contact(env: Mapping[str, str]) -> str | None:
    try:
        return contact_address(env.get("DD_REGISTRY_CONTACT", ""))
    except ValueError as exc:
        raise SettingsError(f"DD_REGISTRY_CONTACT: {exc}") from None


def journal_source(env: Mapping[str, str]) -> JournalSource:
    index = env.get("DD_PID_JOURNALS_REGISTRY", "").strip()
    return JournalSource(Path(index) if index else INDEX)


def registries(env: Mapping[str, str]) -> list[Registry]:
    address = contact(env)
    return [
        doi_registry("DataCite", DataCite(contact=address)),
        doi_registry("Crossref", Crossref(contact=address)),
        orcid_registry(Orcid()),
        ror_registry(ror_sources(env)),
        journal_registry(journal_source(env)),
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
