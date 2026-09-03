"""Command line. An instrument for inspecting runs, not a product.

`argparse` rather than a CLI framework: four subcommands do not justify a dependency a
maintainer has to review, and this is an experiment whose dependency list is part of what is
being judged.

    standards-advisor run samples/soil-chemistry.csv --metadata samples/soil-chemistry.metadata.json
    standards-advisor show-run <run_id>
    standards-advisor export-schemas
    standards-advisor check-model
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from standards_advisor import __version__
from standards_advisor.errors import StandardsAdvisorError
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.provenance.run_dir import RunDirectory
from standards_advisor.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="standards-advisor",
        description=(
            "Recommend controlled vocabularies, ontologies and open formats for a research "
            "dataset (Data Director Blueprint R3). Advisory output only; every result requires "
            "human review."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="experiment root holding prompts/, config/ and schemas/ (default: auto-detected)",
    )
    parser.add_argument(
        "--runs-root", type=Path, default=None, help="where run records are written"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="profile a dataset and ask for advice")
    run_parser.add_argument("files", nargs="+", type=Path, help="data files to profile")
    run_parser.add_argument("--metadata", type=Path, default=None, help="a JSON metadata record")
    run_parser.add_argument("--title", default=None)
    run_parser.add_argument("--description", default=None)
    run_parser.add_argument("--repository", default=None, help="intended deposit repository")
    run_parser.add_argument(
        "--no-checkpoints",
        action="store_true",
        help="use an in-memory checkpointer; the run record is still written",
    )
    run_parser.add_argument("--json", action="store_true", help="print the document to stdout")

    show_parser = subparsers.add_parser("show-run", help="summarise a past run")
    show_parser.add_argument("run_id")
    show_parser.add_argument("--json", action="store_true")

    subparsers.add_parser("export-schemas", help="regenerate schemas/ from the Pydantic models")
    subparsers.add_parser("check-model", help="check the configured model is reachable")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(
        dict(os.environ), project_root=args.project_root, runs_root=args.runs_root
    )

    try:
        if args.command == "run":
            return _cmd_run(args, settings)
        if args.command == "show-run":
            return _cmd_show_run(args, settings)
        if args.command == "export-schemas":
            return _cmd_export_schemas(settings)
        if args.command == "check-model":
            return _cmd_check_model(settings)
    except StandardsAdvisorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # argparse's `required=True` on the subparser makes this unreachable in practice, and
    # `parser.error` exits rather than returning.
    parser.error(f"unknown command {args.command!r}")


def _cmd_run(args: argparse.Namespace, settings: object) -> int:
    from standards_advisor.runner import run_pipeline
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)

    inputs = DatasetInput(
        files=[str(path) for path in args.files],
        metadata_path=str(args.metadata) if args.metadata else None,
        title=args.title,
        description=args.description,
        target_repository=args.repository,
    )

    result = run_pipeline(settings, inputs, use_checkpoints=not args.no_checkpoints)
    document = result.document

    if args.json:
        print(json.dumps(document.model_dump(mode="json") if document else None, indent=2))
        return 0

    print(f"run {result.run_id} — {result.manifest.exit_status}")
    print(f"  record: {result.run_dir.path}")
    if document is None:
        print("  no document was produced")
        return 1

    profile_stage = next(
        (report for report in result.manifest.stages if report.stage == "profile"), None
    )
    if profile_stage is not None:
        counts = profile_stage.counts
        print(
            f"  profiled {counts.get('files', 0)} file(s), "
            f"{counts.get('columns', 0)} column(s), "
            f"{counts.get('rows_sampled', 0)} row(s) sampled"
        )

    print(f"  registry: {document.registry_snapshot.version}", end="")
    print(" (stale)" if document.registry_snapshot.stale else "")
    print(f"  recommendations: {len(document.recommendations)}")
    for item in document.recommendations:
        print(f"    [{item.kind}] {item.resource.name} — {item.resource.registry_id}")
        print(f"      {item.reason}")

    print(f"  nothing found: {len(document.nothing_found)}")
    for absence in document.nothing_found:
        print(f"    [{absence.kind}] {absence.reason}")
        print(f"      {absence.statement}")
        print(f"      → {absence.referral}")

    # Not decoration. C15 makes review mandatory and the document cannot express it as false;
    # the interface saying so is the other half of that.
    print("\n  This output requires human review before it is acted on.")
    return 0


def _cmd_show_run(args: argparse.Namespace, settings: object) -> int:
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)

    run_dir_path = settings.runs_root / args.run_id
    if not run_dir_path.is_dir():
        print(f"error: no run record at {run_dir_path}", file=sys.stderr)
        return 2

    run_dir = RunDirectory(settings.runs_root, args.run_id)
    manifest = run_dir.read_json("manifest")
    document = run_dir.read_json("recommendations")

    if args.json:
        print(json.dumps({"manifest": manifest, "recommendations": document}, indent=2))
        return 0

    if manifest is None:
        print(f"run {args.run_id}: no run.json; the run did not finish")
        return 1

    print(f"run {manifest['run_id']} — {manifest['exit_status']}")
    print(f"  started: {manifest['started_at']}")
    print(f"  agent:   {manifest['agent']['identity']} v{manifest['agent']['version']}")
    print(f"  model:   {manifest['model']['model_id']} ({manifest['model']['calls']} call(s))")
    print(f"  ranking: {manifest['ranking_config']['version']}")
    print(f"  registry: {manifest['registry_route']} @ {manifest['registry_snapshot']['version']}")
    print("  stages:")
    for stage in manifest["stages"]:
        counts = ", ".join(f"{k}={v}" for k, v in sorted(stage["counts"].items()))
        print(f"    {stage['stage']:<9} {stage['status']:<16} {counts}")
        for note in stage["notes"]:
            print(f"      · {note}")
    if manifest["failures"]:
        print("  failures:")
        for failure in manifest["failures"]:
            print(f"    {failure['stage']}: {failure['kind']} — {failure['detail']}")
    if document is not None:
        print(f"  recommendations: {len(document['recommendations'])}")
        print(f"  nothing found:   {len(document['nothing_found'])}")
    print(f"  events: {len(run_dir.read_events())} logged")
    return 0


def _cmd_export_schemas(settings: object) -> int:
    from standards_advisor.schema_export import write_schemas
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)
    changed = write_schemas(settings.schemas_root)
    if not changed:
        print(f"schemas in {settings.schemas_root} are already current")
        return 0
    for path in changed:
        print(f"wrote {path}")
    return 0


def _cmd_check_model(settings: object) -> int:
    """Confirm the configured model can be constructed. Does not call it."""
    from standards_advisor.llm.provider import get_model
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)
    try:
        model = get_model(settings.model_id)
    except Exception as exc:  # noqa: BLE001 — reporting is the point of the command
        print(f"could not build {settings.model_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"{settings.model_id} → {type(model).__name__}")
    # Deliberately understated. Constructing a client does not validate a key, and claiming
    # otherwise would be exactly the kind of unearned confidence this project is arguing against.
    print("the model client was built; no request was made, so credentials are unverified")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
