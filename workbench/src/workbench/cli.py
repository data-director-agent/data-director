"""Command line: list agents, invoke one, lint a run, check its sources, serve the transports.

R3's FAIRsharing snapshot is rebuilt by the agent's own script,
`agents/r3/scripts/build_snapshot.py`; the workbench names no agent."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dd_sdk.contract.models import INPUT_TYPES, InvocationRequest, parse_input
from dd_sdk.tracing import records_from_jsonl
from workbench import grounding, sources
from workbench.conductor import UnknownAgent
from workbench.identity import IdentityError
from workbench.registry import Registry
from workbench.settings import Settings, build_authenticator, build_conductor, build_registry

PROFILE_HELP = "institutional profile file (default: DD_PROFILE, else profiles/default.yaml)"
ACTING_FOR_ID_HELP = (
    "IRI of the human the invocation acts for, e.g. an ORCID iD (default: DD_PRINCIPAL_ID)"
)
ACTING_FOR_NAME_HELP = "name of the human the invocation acts for (default: DD_PRINCIPAL_NAME)"


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


def _settings(args: argparse.Namespace) -> Settings:
    """The environment's settings, with `--profile` and `--acting-for-*` in place of their
    variables if given. Whoever runs the CLI is the operator, so the profile is theirs to choose
    (ADR-0017), and so is the principal they assert (ADR-0018)."""
    settings = Settings.from_env()
    if args.profile:
        settings = replace(settings, profile=Path(args.profile))
    if args.acting_for_id:
        settings = replace(settings, principal_id=args.acting_for_id)
    if args.acting_for_name:
        settings = replace(settings, principal_name=args.acting_for_name)
    return settings


def _add_settings_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--profile", help=PROFILE_HELP)
    p.add_argument("--acting-for-id", help=ACTING_FOR_ID_HELP)
    p.add_argument("--acting-for-name", help=ACTING_FOR_NAME_HELP)


def cmd_invoke(args: argparse.Namespace) -> int:
    settings = _settings(args)
    acting_for = build_authenticator(settings).principal_for(None)
    conductor = build_conductor(settings)
    request = InvocationRequest(
        agent_id=args.agent,
        input=_load_input(args, conductor.registry),
        requirement_ids=args.requirement or [],
    )
    try:
        envelope = conductor.invoke(request, acting_for=acting_for)
    except UnknownAgent as exc:
        sys.exit(str(exc))
    report = conductor.grounding_reports[request.invocation_id]
    print(json.dumps(envelope.to_document(), indent=2))
    print(report.summary(), file=sys.stderr)
    run_dir = conductor.store.run_dir(request.invocation_id)
    print((run_dir / "sources.txt").read_text(encoding="utf-8").rstrip(), file=sys.stderr)
    print(f"run directory: {run_dir}", file=sys.stderr)
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


def cmd_verify(args: argparse.Namespace) -> int:
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    config = Path(args.sources) if args.sources else Settings.from_env().sources_config
    report = sources.check(envelope, sources.Sources.from_config(config))
    print(report.summary())
    return 0 if report.passed else 1


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from workbench.transport.app import build_app

    settings = _settings(args)
    base_url = f"http://{args.host}:{args.port}"
    authenticator = build_authenticator(settings)  # an unset principal stops start-up here
    conductor = build_conductor(settings)
    conductor.workbench_url = settings.workbench_url or base_url  # delegation callback (ADR-0012)
    app = build_app(conductor, authenticator, base_url=base_url)
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
    _add_settings_arguments(p)
    p.add_argument(
        "--requirement", action="append", help="requirement id being exercised (repeatable)"
    )
    p.set_defaults(func=cmd_invoke)

    p = sub.add_parser("lint", help="run the grounding linter over a spans.jsonl and envelope.json")
    p.add_argument("spans")
    p.add_argument("envelope")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser(
        "verify", help="re-hash an envelope.json's evidence against the workbench's source copies"
    )
    p.add_argument("envelope")
    p.add_argument("--sources", help="source configuration (default: sources.yaml)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("serve", help="serve A2A, AG-UI and the viewer")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    _add_settings_arguments(p)
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    except IdentityError as exc:  # no principal configured: nothing may run (ADR-0018)
        sys.exit(f"workbench: {exc}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
