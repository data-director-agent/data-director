"""`dd-mcp-subjects serve`: run the server (README.md).

Settings, from the environment:

- `DD_SUBJECTS_HOSTS`: comma-separated names clients reach the server by, beyond loopback (such
  as a container's service name).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence

import uvicorn

from dd_mcp_subjects.app import LOOPBACK, create_app

DEFAULT_PORT = 8314


def hosts(env: Mapping[str, str]) -> list[str]:
    extra = [h.strip() for h in env.get("DD_SUBJECTS_HOSTS", "").split(",") if h.strip()]
    return [*LOOPBACK, *extra]


def parser() -> argparse.ArgumentParser:
    """`dd-mcp-subjects serve [--port PORT] [--host HOST]`."""
    top = argparse.ArgumentParser(
        prog="dd-mcp-subjects", description=(__doc__ or "").split("\n")[0]
    )
    commands = top.add_subparsers(dest="command", required=True)
    serving = commands.add_parser(
        "serve", help="serve the subject classifications MCP server over HTTP"
    )
    serving.add_argument("--port", type=int, default=DEFAULT_PORT)
    serving.add_argument("--host", default="127.0.0.1")
    return top


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-mcp-subjects`."""
    args = parser().parse_args(argv)
    app = create_app(hosts=hosts(os.environ))
    uvicorn.run(app, port=args.port, host=args.host)
    return 0
