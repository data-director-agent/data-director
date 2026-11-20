"""`dd-deposit-broker serve`: the deposit broker (docs/guide/operations/deposit-broker.md)."""

from __future__ import annotations

import argparse
import logging
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8310


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from dd_deposit_broker.app import DepositBroker, build_app
    from dd_deposit_broker.settings import DepositBrokerSettings, SettingsError

    try:
        broker = DepositBroker.open(DepositBrokerSettings.from_env())
    except SettingsError as exc:
        sys.exit(f"dd-deposit-broker: {exc}")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(build_app(broker), host=args.host, port=args.port, server_header=False)
    return 0


TRY_TOKEN = "DD_DEPOSIT_BROKER_TRY_TOKEN"


def cmd_try(args: argparse.Namespace) -> int:
    """Make one draft with a person's token and delete it again: the check an operator runs
    against a sandbox before turning depositing on (docs/guide/operations/deposit-broker.md)."""
    import json
    import os

    import httpx

    from dd_deposit_broker import zenodo
    from dd_deposit_broker.reasons import Refused
    from dd_deposit_broker.settings import base_url

    token = (os.environ.get(TRY_TOKEN) or "").strip()
    if not token:
        sys.exit(f"dd-deposit-broker: set {TRY_TOKEN} to a token with the deposit:write scope")
    root = base_url(args.base_url)
    item = {
        "metadata": {
            "upload_type": "dataset",
            "title": "Data Director deposit check (safe to delete)",
            "creators": [{"name": "Data Director"}],
            "description": "A draft made by dd-deposit-broker try, and deleted at once.",
            "access_right": "open",
            "license": "cc-by-4.0",
        }
    }
    try:
        zenodo.check(root, token)
        answer = zenodo.create_draft(
            root,
            token,
            item=json.dumps(item).encode(),
            package=b"PK\x05\x06" + bytes(18),
            package_name="check.zip",
        )
    except Refused as refused:
        sys.exit(f"dd-deposit-broker: refused: {refused.reason.value}")
    sys.stdout.write(f"draft {answer.deposit_id} made at {answer.draft_url}\n")
    if not args.keep:
        with httpx.Client(timeout=zenodo.TIMEOUT_S) as client:
            deleted = client.delete(
                f"{root}/deposit/depositions/{answer.deposit_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        sys.stdout.write(f"draft deleted: {deleted.status_code in (201, 202, 204)}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-deposit-broker",
        description="Data Director deposit broker: makes draft deposits on people's own accounts",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve", help="serve the deposit broker")
    # Only /connect/ may be exposed, through the reverse proxy; /deposits is for the harness on
    # this host (docs/guide/operations/deposit-broker.md).
    p.add_argument("--host", default=DEFAULT_HOST, help=f"default {DEFAULT_HOST}")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    p.set_defaults(func=cmd_serve)
    t = sub.add_parser("try", help=f"make one draft with the token in {TRY_TOKEN}, then delete it")
    t.add_argument("--base-url", default="https://sandbox.zenodo.org/api")
    t.add_argument("--keep", action="store_true", help="keep the draft, to look at it")
    t.set_defaults(func=cmd_try)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
