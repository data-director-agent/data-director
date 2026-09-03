"""Stage 1 — elicit (§8). Asks the researcher what no file can tell us.

Only pre-collection runs have anything to ask. Before data exists there is nothing to profile,
so the facets §5.2 searches on — subject, field of research, entity scope — cannot be inferred
at all. §5.1 tier 2 was meant to obtain them by having a model pick from the registry's own term
lists; that route is unavailable, because with the default registry route `list_terms()` raises.
So asking is not a weaker substitute for tier 2 here. It is the only honest source, and R5 says
as much: variable definitions, units, missing value codes, study design and collection
procedures "cannot be inferred and require direct researcher input".

**This node re-runs from the top when the graph resumes.** LangGraph replays an interrupted node
rather than continuing inside it, with `interrupt()` returning the resume value instead of
raising. Two rules follow, and breaking either is silent:

1. Everything before the `interrupt()` must be deterministic. The question set is therefore
   fixed, versioned configuration rather than anything a model writes — a model-generated
   question would be generated twice, and the researcher could be shown one set of questions and
   have their answers validated against another.
2. Nothing before the `interrupt()` may have side effects. In particular the stage report is
   written by `stage()` on the resumed pass only, which is what `support.stage`'s `GraphBubbleUp`
   clause exists to guarantee.

No conditional edge. The node runs on every path and returns early when there is nothing to ask,
exactly as `profile` does for its unimplemented tiers, so the graph keeps its one unconditional
line and `elicit` still contributes a stage report to every run — which `test_provenance` relies
on, since it compares the manifest's stages against `list(StageName)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt

from standards_advisor.ids import utc_now
from standards_advisor.jsonio import read_json_object, text_list
from standards_advisor.models.common import StageName, StageStatus
from standards_advisor.models.elicitation import (
    Answer,
    ElicitedContext,
    InterruptRequest,
    Question,
)
from standards_advisor.nodes.support import merge, stage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.nodes.support import StageRun
    from standards_advisor.state import PipelineState


def elicit_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    inputs = state["inputs"]

    with stage(ctx, StageName.ELICIT) as run:
        questions = ctx.intake.questions_for(inputs.phase)

        if not questions:
            # Nothing to ask outside pre-collection. `EMPTY` is exactly right — its docstring is
            # "ran correctly and produced nothing" — and saying so beats a stage that silently
            # does nothing on the path almost every run takes. Note this is an early *exit from
            # the block*, not from the function: `merge` reads the report that `stage()` writes
            # on the way out, so it cannot be called from in here.
            run.status = StageStatus.EMPTY
            run.note(f"no intake questions apply to a {inputs.phase.value} run")
            run.payload = None
        else:
            run.note(f"intake question set {ctx.intake.version}")
            run.payload = _ask(state, ctx, run, questions)

    return merge(run, answers=run.payload)


def _ask(
    state: PipelineState,
    ctx: RunContext,
    run: StageRun,
    questions: list[Question],
) -> ElicitedContext:
    """Put the questions, pausing the graph if no answers were supplied up front."""
    asked_at = utc_now().isoformat()
    supplied = _supplied_answers(state["inputs"].answers_path, run)

    if supplied is None:
        # Pause. Resuming re-enters `elicit_node` from the top and this call returns the answers
        # instead of suspending — see the module docstring. Dumped to plain JSON because the
        # payload goes into a checkpoint and out to whatever is driving the run.
        raw: Any = interrupt(
            InterruptRequest(
                run_id=state["run_id"],
                asked_at=asked_at,
                intake_version=ctx.intake.version,
                questions=questions,
            ).model_dump(mode="json")
        )
        interactive = True
    else:
        raw = supplied
        interactive = False

    context = _build_context(
        questions=questions,
        raw=raw,
        asked_at=asked_at,
        intake_version=ctx.intake.version,
        intake_sha256=ctx.intake.sha256,
        interactive=interactive,
        run=run,
    )

    run.counts = {
        "questions": len(questions),
        "answered": sum(1 for answer in context.answers if not answer.skipped),
        "skipped": sum(1 for answer in context.answers if answer.skipped),
    }
    if all(answer.skipped for answer in context.answers):
        # Every question skipped is a valid outcome and a bleak one: the four searches will run
        # on almost nothing. Recording it as `empty` lets an abstention say why.
        run.status = StageStatus.EMPTY
        run.note("every intake question was skipped; the searches will have no facets")

    ctx.run_dir.write_json("answers", context.model_dump(mode="json"))
    return context


def _supplied_answers(answers_path: str | None, run: StageRun) -> dict[str, Any] | None:
    """Answers given up front, if any. A missing or malformed file is recorded, not raised.

    Returning `None` means "ask"; returning a mapping means "do not pause". A malformed file
    therefore cannot silently become an interactive prompt in a context that has no terminal —
    it becomes an empty mapping and a recorded failure, and the run completes having asked
    nothing and said so.
    """
    if answers_path is None:
        return None
    path = Path(answers_path)
    if not path.is_file():
        run.fail("answers_missing", f"{answers_path} is not a readable file")
        return {}
    loaded, error = read_json_object(path)
    if error is not None:
        run.fail("answers_unreadable", f"{answers_path}: {error}")
        return {}
    return loaded


def _build_context(
    *,
    questions: list[Question],
    raw: Any,
    asked_at: str,
    intake_version: str,
    intake_sha256: str,
    interactive: bool,
    run: StageRun,
) -> ElicitedContext:
    """Match a raw answer mapping onto the question set.

    Iterates the *questions*, not the answers. An answer for a question that does not exist is
    recorded and dropped rather than kept, and a question with no answer becomes an explicit
    skip — so the recorded set always has exactly one entry per question asked, whatever the
    caller sent.
    """
    mapping = raw if isinstance(raw, dict) else {}
    if raw is not None and not isinstance(raw, dict):
        run.fail("answers_unexpected", f"expected an object of answers, got {type(raw).__name__}")

    answers: list[Answer] = []
    for question in questions:
        values = _values(mapping.get(question.id))
        if not question.multiple and len(values) > 1:
            run.note(f"{question.id} takes one answer; keeping the first of {len(values)}")
            values = values[:1]
        answers.append(
            Answer(
                question_id=question.id,
                facet=question.facet,
                values=values,
                skipped=not values,
            )
        )

    unknown = sorted(set(mapping) - {question.id for question in questions})
    for key in unknown:
        run.fail("answer_unknown_question", f"no question with id {key!r} was asked")

    return ElicitedContext(
        asked_at=asked_at,
        answered_at=utc_now().isoformat(),
        intake_version=intake_version,
        intake_sha256=intake_sha256,
        answers=answers,
        interactive=interactive,
    )


def _values(value: Any) -> list[str]:
    """One answer as a list of non-empty strings.

    `jsonio.text_list` is lenient about a bare string where a list was expected, which is what
    is wanted here: these answers are typed by a person or written into a file by hand, and
    rejecting `"soil science"` where `["soil science"]` was expected would be pedantry with a
    traceback attached.
    """
    return text_list(value)
