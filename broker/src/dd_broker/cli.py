"""`dd-model-broker serve`: the model broker (docs/guide/operations/model-broker.md)."""

from __future__ import annotations

import argparse
import logging
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8300


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from dd_broker.app import Broker, build_app
    from dd_broker.settings import BrokerSettings, SettingsError

    try:
        broker = Broker.open(BrokerSettings.from_env())
    except SettingsError as exc:
        sys.exit(f"dd-model-broker: {exc}")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(build_app(broker), host=args.host, port=args.port, server_header=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-model-broker",
        description="Data Director model broker: makes model calls on people's own accounts",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve", help="serve the broker's interface for agents")
    # Agent ports, and this one, must not be exposed beyond the host or a private network
    # (docs/specs/transport.md, TODO(#17)).
    p.add_argument("--host", default=DEFAULT_HOST, help=f"default {DEFAULT_HOST}")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    p.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
