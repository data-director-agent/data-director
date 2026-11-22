"""`dd-mcp-spdx serve`: run the server (README.md).

Settings, from the environment:

- `DD_SPDX_HOSTS`: comma-separated names clients reach the server by, beyond loopback (such as a
  container's service name).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence

import uvicorn

from dd_mcp_spdx.app import LOOPBACK, create_app

DEFAULT_PORT = 8312


def hosts(env: Mapping[str, str]) -> list[str]:
    extra = [h.strip() for h in env.get("DD_SPDX_HOSTS", "").split(",") if h.strip()]
    return [*LOOPBACK, *extra]


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-mcp-spdx`."""
    parser = argparse.ArgumentParser(prog="dd-mcp-spdx", description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the SPDX licence list MCP server over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(hosts=hosts(os.environ)), host=args.host, port=args.port)
    return 0
