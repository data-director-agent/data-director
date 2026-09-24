"""Command line: list agents, invoke one, lint a run, serve the transports.

R3's FAIRsharing snapshot is rebuilt by the agent's own script,
`agents/r3/scripts/build_snapshot.py`; the workbench names no agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dd_sdk.contract.models import INPUT_TYPES, InvocationRequest, parse_input
from dd_sdk.tracing import records_from_jsonl
from workbench import grounding
from workbench.conductor import UnknownAgent
from workbench.registry import Registry
from workbench.settings import Settings, build_conductor, build_registry


def _load_input(args: argparse.Namespace, registry: Registry) -> Any:
    """Resolve the input class: the document's schema_class, then --input-type, then the agent's
    sole accepted class. Anything else is a usage error listing what the agent accepts."""
    doc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    agent = registry.get(args.agent)
    accepts = agent.spec.accepts_names() if agent else tuple(INPUT_TYPES)
    if "schema_class" not in doc:
        if args.input_type:
            doc["schema_class"] = args.input_type
        elif len(accepts) == 1:
            doc["schema_class"] = accepts[0]
        else:
            sys.exit(
                f"{args.input} has no schema_class and {args.agent} accepts more than one input "
                f"class ({', '.join(accepts)}); pass --input-type"
            )
    try:
        return parse_input(doc)
    except ValidationError as exc:
        sys.exit(f"{args.input} is not a valid {doc.get('schema_class')}: {exc}")


def cmd_agents(args: argparse.Namespace) -> int:
    registry = build_registry(Settings.from_env())
    if args.json:
        print(
            json.dumps(
                {"agents": registry.manifest(), "unavailable": registry.unavailable}, indent=2
            )
        )
        return 0
    rows = [
        (
            m["agent_id"],
            m["version"],
            m["grounding_mode"],
            ", ".join(m["accepts"]),
            m["payload"] or "—",
            ", ".join(m["requirement_ids"]),
        )
        for m in registry.manifest()
    ]
    head = ("agent_id", "version", "mode", "accepts", "payload", "requirements")
    widths = [max(len(str(r[i])) for r in (head, *rows)) for i in range(len(head))]
    for r in (head, *rows):
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)).rstrip())
    for name, reason in registry.unavailable.items():
        print(f"\n[{name}] unavailable: {reason}")
    return 0


def cmd_invoke(args: argparse.Namespace) -> int:
    conductor = build_conductor(Settings.from_env())
    request = InvocationRequest(
        agent_id=args.agent,
        policy_bundle_ref=args.profile,
        input=_load_input(args, conductor.registry),
        requirement_ids=args.requirement or [],
    )
    try:
        envelope = conductor.invoke(request)
    except UnknownAgent as exc:
        sys.exit(str(exc))
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

    settings = Settings.from_env()
    base_url = f"http://{args.host}:{args.port}"
    conductor = build_conductor(settings)
    conductor.workbench_url = settings.workbench_url or base_url  # delegation callback (ADR-0012)
    app = build_app(conductor, base_url=base_url)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workbench", description="Data Director Workbench")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("agents", help="list the registered agents and what each accepts")
    p.add_argument("--json", action="store_true", help="print the manifest as JSON")
    p.set_defaults(func=cmd_agents)

    p = sub.add_parser("invoke", help="run one agent over an input document and print the envelope")
    p.add_argument("--agent", required=True, help="agent id; see `workbench agents`")
    p.add_argument("--input", required=True, help="path to an input JSON document")
    p.add_argument(
        "--input-type",
        choices=sorted(INPUT_TYPES),
        help="input class, if the document has no schema_class and the agent accepts several",
    )
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

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
