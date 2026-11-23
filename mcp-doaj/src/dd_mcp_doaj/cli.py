"""`dd-mcp-doaj serve`: run the server (README.md).

Settings, from the environment:

- `DD_DOAJ_HOSTS`: comma-separated names clients reach the server by, beyond loopback (such as a
  container's service name).
- `DD_REGISTRY_CONTACT`: the operators' contact address (never a person's own), added to the
  User-Agent as `mailto:`. Unset, no address is sent.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence

import uvicorn

from dd_mcp_doaj.app import LOOPBACK, create_app
from dd_mcp_doaj.journals import Doaj
from dd_mcp_doaj.tools import Tools

DEFAULT_PORT = 8313


def hosts(env: Mapping[str, str]) -> list[str]:
    extra = [h.strip() for h in env.get("DD_DOAJ_HOSTS", "").split(",") if h.strip()]
    return [*LOOPBACK, *extra]


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-mcp-doaj`."""
    parser = argparse.ArgumentParser(prog="dd-mcp-doaj", description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the DOAJ MCP server over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    contact = os.environ.get("DD_REGISTRY_CONTACT", "").strip() or None
    tools = Tools(Doaj(contact=contact))
    uvicorn.run(create_app(tools, hosts=hosts(os.environ)), host=args.host, port=args.port)
    return 0
