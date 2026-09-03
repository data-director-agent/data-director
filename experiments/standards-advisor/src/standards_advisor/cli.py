"""Command line. An instrument for inspecting runs, not a product.

`argparse` rather than a CLI framework: six subcommands do not justify a dependency a
maintainer has to review, and this is an experiment whose dependency list is part of what is
being judged.

    standards-advisor run samples/soil-chemistry.csv --metadata samples/soil-chemistry.metadata.json
    standards-advisor plan --dictionary samples/planned/soil-survey.dictionary.json \
        --readme samples/planned/README.md
    standards-advisor resume <run_id> --answers answers.json
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
from typing import TYPE_CHECKING

from standards_advisor import __version__
from standards_advisor.errors import StandardsAdvisorError
from standards_advisor.jsonio import read_json_object
from standards_advisor.models.elicitation import InterruptRequest
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.provenance.run_dir import RunDirectory
from standards_advisor.settings import load_settings

if TYPE_CHECKING:
    # `runner` pulls in LangGraph, so every command imports it lazily inside its own body. This
    # annotation must not undo that.
    from standards_advisor.runner import RunResult


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

    plan_parser = subparsers.add_parser(
        "plan",
        help="advise on a dataset that does not exist yet (Blueprint phase 1)",
        description=(
            "Ask for advice before data collection begins, from a README and a draft data "
            "dictionary (Frictionless Table Schema). Without --answers this pauses to ask you "
            "about the project, then continues; the questions and your answers are recorded "
            "with the run."
        ),
    )
    plan_parser.add_argument(
        "--dictionary",
        type=Path,
        required=True,
        help="a draft data dictionary as Frictionless Table Schema",
    )
    plan_parser.add_argument("--readme", type=Path, default=None, help="a README for the project")
    plan_parser.add_argument(
        "--answers",
        type=Path,
        default=None,
        help="intake answers as JSON, to run without pausing to ask",
    )
    plan_parser.add_argument("--title", default=None)
    plan_parser.add_argument("--description", default=None)
    plan_parser.add_argument("--repository", default=None, help="intended deposit repository")
    plan_parser.add_argument("--json", action="store_true", help="print the document to stdout")

    resume_parser = subparsers.add_parser(
        "resume", help="continue a run that paused to ask a question"
    )
    resume_parser.add_argument("run_id")
    resume_parser.add_argument(
        "--answers", type=Path, default=None, help="intake answers as JSON, instead of prompting"
    )
    resume_parser.add_argument("--json", action="store_true")

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
        if args.command == "plan":
            return _cmd_plan(args, settings)
        if args.command == "resume":
            return _cmd_resume(args, settings)
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
    return _report(result, as_json=args.json)


def _report(result: RunResult, *, as_json: bool) -> int:
    """Print a finished run. Shared by `run`, `plan` and `resume`."""
    document = result.document

    if as_json:
        print(json.dumps(document.model_dump(mode="json") if document else None, indent=2))
        return 0

    print(f"run {result.run_id} — {result.manifest.exit_status}")
    print(f"  record: {result.run_dir.path}")
    if document is None:
        print("  no document was produced")
        return 1

    print(f"  phase: {document.phase.value}")
    profile_stage = next(
        (report for report in result.manifest.stages if report.stage == "profile"), None
    )
    if profile_stage is not None:
        counts = profile_stage.counts
        if "planned_variables" in counts:
            print(
                f"  read {counts.get('planned_variables', 0)} planned variable(s) from the "
                "data dictionary; no data was read, because none exists yet"
            )
        else:
            print(
                f"  profiled {counts.get('files', 0)} file(s), "
                f"{counts.get('columns', 0)} column(s), "
                f"{counts.get('rows_sampled', 0)} row(s) sampled"
            )

    elicit_stage = next(
        (report for report in result.manifest.stages if report.stage == "elicit"), None
    )
    if elicit_stage is not None and elicit_stage.counts.get("questions"):
        counts = elicit_stage.counts
        print(
            f"  intake: {counts.get('answered', 0)} of {counts.get('questions', 0)} question(s) "
            f"answered, {counts.get('skipped', 0)} skipped"
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


def _cmd_plan(args: argparse.Namespace, settings: object) -> int:
    """Blueprint phase 1: advise on a dataset that does not exist yet (§8)."""
    from standards_advisor.models.common import LifecyclePhase
    from standards_advisor.runner import resume_pipeline, run_pipeline
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)

    inputs = DatasetInput(
        phase=LifecyclePhase.PRE_COLLECTION,
        dictionary_path=str(args.dictionary),
        readme_path=str(args.readme) if args.readme else None,
        answers_path=str(args.answers) if args.answers else None,
        title=args.title,
        description=args.description,
        target_repository=args.repository,
    )

    result = run_pipeline(settings, inputs)

    if result.awaiting_input:
        assert result.interrupt is not None
        answers = _ask_interactively(result.interrupt)
        if answers is None:
            # No terminal to ask at. The run is paused and resumable, so say how — exiting with
            # an error and no explanation would leave a half-finished record and no way back.
            _report_pending(result.interrupt, result.run_id)
            return 3
        result = resume_pipeline(settings, result.run_id, answers)

    return _report(result, as_json=args.json)


def _cmd_resume(args: argparse.Namespace, settings: object) -> int:
    """Continue a run that paused to ask a question (§8)."""
    from standards_advisor.runner import resume_pipeline
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)

    if args.answers is not None:
        loaded, error = read_json_object(args.answers)
        if error is not None:
            print(f"error: {args.answers} {error}", file=sys.stderr)
            return 2
        answers = loaded
    else:
        pending = _pending_questions(settings, args.run_id)
        if pending is None:
            print(f"error: run {args.run_id} is not waiting for answers", file=sys.stderr)
            return 2
        asked = _ask_interactively(pending)
        if asked is None:
            _report_pending(pending, args.run_id)
            return 3
        answers = asked

    result = resume_pipeline(settings, args.run_id, answers)
    return _report(result, as_json=args.json)


def _pending_questions(settings: object, run_id: str) -> InterruptRequest | None:
    """The questions a paused run is waiting on, read back from its own record.

    Reconstructed from `run.json` and the intake configuration rather than from the checkpoint:
    the checkpoint's format belongs to a dependency, and the run record is ours.
    """
    from standards_advisor.intake import load_intake_config
    from standards_advisor.models.common import LifecyclePhase
    from standards_advisor.runner import AWAITING_INPUT
    from standards_advisor.settings import Settings

    assert isinstance(settings, Settings)

    run_dir = RunDirectory(settings.runs_root, run_id)
    manifest = run_dir.read_json("manifest")
    if not isinstance(manifest, dict) or manifest.get("exit_status") != AWAITING_INPUT:
        return None

    intake = load_intake_config(settings.intake_config_path())
    questions = intake.questions_for(LifecyclePhase.PRE_COLLECTION)
    if not questions:
        return None
    return InterruptRequest(
        run_id=run_id,
        asked_at=str(manifest.get("started_at", "")),
        intake_version=intake.version,
        questions=questions,
    )


def _ask_interactively(pending: InterruptRequest) -> dict[str, list[str]] | None:
    """Put the questions at the terminal. `None` when there is no terminal to put them at.

    Returning `None` rather than prompting anyway is what keeps `plan` usable in a script or in
    CI: `input()` on a closed stdin raises `EOFError`, which would surface as a traceback on a
    run that is in fact perfectly resumable.
    """
    if not sys.stdin.isatty():
        return None

    print("\nA few questions about the project. Press enter to skip any of them.\n")
    answers: dict[str, list[str]] = {}
    for question in pending.questions:
        print(f"  {question.text}")
        print(f"    why: {question.why}")
        if question.example:
            print(f"    e.g. {question.example}")
        if question.multiple:
            print("    (separate several answers with commas)")
        try:
            raw = input("  > ").strip()
        except EOFError, KeyboardInterrupt:
            print("\ninterrupted; the run is paused and can be resumed", file=sys.stderr)
            return None
        print()
        values = [item.strip() for item in raw.split(",") if item.strip()] if raw else []
        answers[question.id] = values
    return answers


def _report_pending(pending: InterruptRequest, run_id: str) -> None:
    """Print the questions and how to answer them, for a run that cannot be asked here."""
    print(f"run {run_id} is waiting for answers to {len(pending.questions)} question(s):")
    for question in pending.questions:
        print(f"  {question.id}: {question.text}")
    print(
        f"\nNo terminal is attached, so nothing was asked. Write the answers as a JSON object "
        f"keyed by the ids above, then:\n"
        f"  standards-advisor resume {run_id} --answers answers.json"
    )


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
