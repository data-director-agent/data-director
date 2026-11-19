"""`dd-admin serve`: the admin service, on loopback only (docs/guide/operations/admin.md)."""

from __future__ import annotations

import argparse
import ipaddress
import sys

from dd_harness.settings import SettingsError

DEFAULT_PORT = 8200


def loopback(host: str) -> bool:
    """Whether `host` is a loopback address or `localhost`: the only places the service listens,
    since it has no sign-in of its own."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from dd_admin.app import Admin, build_app
    from dd_admin.settings import AdminSettings

    if not loopback(args.host):
        sys.exit(
            f"dd-admin: refusing to listen on {args.host}: the admin service has no sign-in, so "
            "it listens on loopback only; reach it through an SSH tunnel "
            "(docs/guide/operations/admin.md)"
        )
    try:
        admin = Admin.open(AdminSettings.from_env())
    except SettingsError as exc:
        sys.exit(f"dd-admin: {exc}")
    uvicorn.run(build_app(admin), host=args.host, port=args.port, server_header=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-admin", description="Data Director admin: a read-only view of a deployment"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve", help="serve the admin pages on loopback")
    p.add_argument("--host", default="127.0.0.1", help="a loopback address (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    p.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
