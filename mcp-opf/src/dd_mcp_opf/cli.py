"""`dd-mcp-opf serve` runs the server; `dd-mcp-opf check` tries the route (README.md).

Read from the environment:

- `OPEN_POLICY_FINDER_API_KEY`, or `OPEN_POLICY_FINDER_API_KEY_FILE` naming a file that holds it:
  a free key from Jisc. A relative file name is read under `CREDENTIALS_DIRECTORY`. With no key
  the server still starts, and each call says one is needed.
- `DD_OPF_HOSTS`: extra host names, comma-separated, that clients may use to reach the server.
- `DD_REGISTRY_CONTACT`: the operators' contact address, never a person's own, sent in the
  User-Agent as `mailto:`; unset, none is sent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import uvicorn

from dd_mcp_opf.app import LOOPBACK, create_app
from dd_mcp_opf.client import KEY_NAME, ItemType, OpenPolicyFinder, OpfUnavailableError
from dd_mcp_opf.tools import Tools

DEFAULT_PORT = 8314
# Records that should be found, chosen from the pilot workshop's cases.
CHECKS: tuple[tuple[str, ItemType, str], ...] = (
    ("search", "funder", "Natural Environment Research Council"),
    ("search", "funder", "Economic and Social Research Council"),
    ("search", "publisher", "Elsevier"),
    ("search", "publication", "Science of the Total Environment"),
    ("fetch", "publication", "0048-9697"),
)


class SettingsError(Exception):
    """A setting has a value the server cannot use. The message names it."""


def api_key(env: Mapping[str, str]) -> str | None:
    """The key in `OPEN_POLICY_FINDER_API_KEY`, or in the file `..._FILE` names, or None."""
    value = env.get(KEY_NAME, "").strip()
    name = KEY_NAME + "_FILE"
    file = env.get(name, "").strip()
    if value and file:
        raise SettingsError(f"set {KEY_NAME} or {name}, not both")
    if value or not file:
        return value or None
    path = Path(file)
    if not path.is_absolute():
        directory = env.get("CREDENTIALS_DIRECTORY", "").strip()
        if not directory:
            raise SettingsError(f"{name}={file} is relative and CREDENTIALS_DIRECTORY is not set")
        path = Path(directory) / path
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SettingsError(f"{name}: cannot read {path}: {exc.strerror}") from None
    if not text or any(c.isspace() for c in text):
        raise SettingsError(f"{name}: {path} does not hold one key")
    return text


def hosts(env: Mapping[str, str]) -> list[str]:
    extra = [h.strip() for h in env.get("DD_OPF_HOSTS", "").split(",") if h.strip()]
    return [*LOOPBACK, *extra]


def check(source: OpenPolicyFinder, record_to: Path | None = None) -> int:
    """Ask the live route for each of `CHECKS` and say what came back. With `record_to`, write
    each answer there, as projected, for use as a test fixture once read and trimmed."""
    failures = 0
    for n, (how, item_type, text) in enumerate(CHECKS, start=1):
        try:
            if how == "search":
                found = source.search(item_type, text)
            else:
                one = source.fetch(item_type, text)
                found = [one] if one else []
        except OpfUnavailableError as exc:
            failures += 1
            sys.stdout.write(f"{how} {item_type} {text!r}: unavailable ({exc})\n")
            continue
        names = "; ".join(str((r["names"] or [r["id"]])[0]) for r in found[:5]) or "(none)"
        policies = sum(len(r["policies"]) for r in found)
        sys.stdout.write(
            f"{how} {item_type} {text!r}: {len(found)} record(s), {policies} policies: {names}\n"
        )
        if record_to is not None:
            record_to.mkdir(parents=True, exist_ok=True)
            out = record_to / f"opf-check-{n}-{item_type}.json"
            out.write_text(json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-mcp-opf`."""
    parser = argparse.ArgumentParser(prog="dd-mcp-opf", description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the Open Policy Finder MCP server over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    run = sub.add_parser("check", help="ask the live API for a few known records")
    run.add_argument("--record", type=Path, help="write each answer, as projected, to this folder")
    args = parser.parse_args(argv)
    contact = os.environ.get("DD_REGISTRY_CONTACT", "").strip() or None
    try:
        key = api_key(os.environ)
        source = OpenPolicyFinder(key, contact=contact) if key else None
    except (SettingsError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    if args.command == "check":
        if source is None:
            sys.stderr.write(f"set {KEY_NAME} to check the route\n")
            return 2
        return check(source, args.record)
    if source is None:
        sys.stderr.write(f"warning: {KEY_NAME} is not set, so every call will say it is needed\n")
    uvicorn.run(create_app(Tools(source), hosts=hosts(os.environ)), host=args.host, port=args.port)
    return 0
