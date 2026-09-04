"""Command line: invoke an agent, lint a run, serve the transports, build the snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workbench import grounding
from workbench.contract.models import DatasetProfile, InvocationRequest
from workbench.settings import Settings, build_conductor
from workbench.tracing import records_from_jsonl


def cmd_invoke(args: argparse.Namespace) -> int:
    profile = DatasetProfile.model_validate(
        json.loads(Path(args.input).read_text(encoding="utf-8"))
    )
    request = InvocationRequest(
        agent_id=args.agent,
        policy_bundle_ref=args.profile,
        input=profile,
        requirement_ids=args.requirement or [],
    )
    conductor = build_conductor(Settings.from_env())
    envelope = conductor.invoke(request)
    report = conductor.grounding_reports[request.invocation_id]
    print(json.dumps(envelope.to_document(), indent=2))
    print(report.summary(), file=sys.stderr)
    print(f"run directory: {conductor.store.run_dir(request.invocation_id)}", file=sys.stderr)
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    lines = [
        json.loads(line)
        for line in Path(args.spans).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    report = grounding.lint(records_from_jsonl(lines), envelope)
    print(report.summary())
    return 0 if report.passed else 1


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from workbench.transport.app import build_app

    app = build_app(
        build_conductor(Settings.from_env()), base_url=f"http://{args.host}:{args.port}"
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import build_snapshot

    return int(build_snapshot.main(args.ids, args.out))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workbench", description="Data Director Workbench")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("invoke", help="run one agent over a dataset profile and print the envelope")
    p.add_argument("--agent", required=True, help="r3.standards-advisor or stub.abstain")
    p.add_argument("--input", required=True, help="path to a DatasetProfile JSON document")
    p.add_argument("--profile", default="profile:default", help="policy bundle reference")
    p.add_argument(
        "--requirement", action="append", help="requirement id being exercised (repeatable)"
    )
    p.set_defaults(func=cmd_invoke)

    p = sub.add_parser("lint", help="run the grounding linter over a spans.jsonl and envelope.json")
    p.add_argument("spans")
    p.add_argument("envelope")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("serve", help="serve A2A, AG-UI and the shell")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser(
        "snapshot",
        help="(re)build data/fairsharing/snapshot.jsonl from ids.txt via the public record route",
    )
    p.add_argument("--ids", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_snapshot)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
