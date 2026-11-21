"""`dd-mcp-fairsharing serve`: run the server (README.md).

Settings, from the environment:

- `FAIRSHARING_LOGIN`, `FAIRSHARING_PASSWORD`: a FAIRsharing account, needed only by
  `search_records`. Without them `get_record` still works.
- `DD_FAIRSHARING_HOSTS`: comma-separated names clients reach the server by, beyond loopback
  (such as a container's service name).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence

import uvicorn

from dd_mcp_fairsharing.app import LOOPBACK, create_app
from dd_mcp_fairsharing.client import Fairsharing
from dd_mcp_fairsharing.tools import Tools

DEFAULT_PORT = 8311


def hosts(env: Mapping[str, str]) -> list[str]:
    extra = [h.strip() for h in env.get("DD_FAIRSHARING_HOSTS", "").split(",") if h.strip()]
    return [*LOOPBACK, *extra]


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-mcp-fairsharing`."""
    parser = argparse.ArgumentParser(
        prog="dd-mcp-fairsharing", description=(__doc__ or "").split("\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve the FAIRsharing MCP server over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    app = create_app(Tools(Fairsharing()), hosts(os.environ))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
