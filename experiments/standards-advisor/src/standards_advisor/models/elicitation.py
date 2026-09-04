"""What the `elicit` stage asks, and what the researcher answered (§8).

An internal stage payload, like `models.candidates` — not part of the §6 published contract, so
it is deliberately absent from `schema_export.EXPORTS`. It is still written to the run directory
as `answers.json`, because R10 requires every action the agent takes on metadata be recordable,
and "we asked these questions and were told this" is the whole of what the stage did.

Why a facet enum rather than string keys: an answer is only useful if something maps it onto a
profile field, and a typo in a string key would fail silently by filling nothing. `IntakeFacet`
makes that mapping exhaustive and type-checked, so adding a question without wiring up its
destination does not compile.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from standards_advisor.models.common import Derivation, Frozen, Term


class IntakeFacet(StrEnum):
    """What a question's answer fills in.

    The first three are the facets §5.2 searches on and §5.1 tier 2 was meant to obtain by
    having a model pick from the registry's own lists. That route is unavailable — with the
    default registry the term lists cannot be fetched at all — so asking the researcher is not
    a lesser substitute here, it is the only honest source.

    The last four come from R5's list of elements that "cannot be inferred and require direct
    researcher input".
    """

    SUBJECT = "subject"
    FIELD_OF_RESEARCH = "field_of_research"
    ENTITY_SCOPE = "entity_scope"
    """What kinds of thing the values will name — organisms, places, occupations, materials.
    Separates a vocabulary covering the right subject from one covering the right subject *and*
    the right kind of value."""

    MEASURED_VARIABLE = "measured_variable"
    FORMAT_PLANNED = "format_planned"
    TARGET_REPOSITORY = "target_repository"
    STUDY_DESIGN = "study_design"
    COLLECTION_METHOD = "collection_method"


class Question(Frozen):
    """One intake question, as loaded from the versioned question set."""

    id: str
    facet: IntakeFacet
    text: str
    why: str
    """What this question is for, shown to the researcher. §8.2 of the Blueprint says the
    workflow belongs to the researcher and the agent's role is to assist rather than direct —
    a question that cannot say why it is being asked has no business being asked."""
    multiple: bool = True
    """Whether more than one answer is expected."""
    example: str | None = None


class Answer(Frozen):
    """What came back for one question.

    `skipped` is a real answer, not a missing one. "I do not know what field of research this
    is" is information, and it must not be recorded as though the question were never put — the
    §5.3 rules skip a missing input rather than scoring it zero, and this is the same idea one
    stage earlier.
    """

    question_id: str
    facet: IntakeFacet
    values: list[str] = Field(default_factory=list)
    skipped: bool = False


class ElicitedContext(Frozen):
    """The answers, and enough about the asking to audit it (R10).

    Held in graph state and therefore checkpointed. LangGraph serialises state models with a
    module-path marker, so moving or renaming this class breaks resuming an older checkpoint —
    which for §8 is not hypothetical, since the checkpoint is written by one process and read by
    another across a human-length pause. `test_provenance` round-trips it for that reason.
    """

    asked_at: str
    """When the questions were put. Separate from the stage's own timings, which measure
    validation only: the stage pauses *outside* its own `stage()` block, so the researcher's
    thinking time is deliberately not counted as time the pipeline spent working."""
    answered_at: str
    intake_version: str
    intake_sha256: str
    """Which question set was in force, hashed — the same discipline as prompts and weights, so
    an old run stays resolvable to the questions actually asked."""

    answers: list[Answer] = Field(default_factory=list)
    interactive: bool = True
    """False when answers were supplied up front rather than asked for. Recorded because it
    changes what the answers are evidence of."""

    def values_for(self, facet: IntakeFacet) -> list[str]:
        """Every non-skipped value given for one facet, in order, without duplicates."""
        seen: dict[str, None] = {}
        for answer in self.answers:
            if answer.facet is facet and not answer.skipped:
                for value in answer.values:
                    seen.setdefault(value, None)
        return list(seen)

    def terms_for(self, facet: IntakeFacet) -> list[Term]:
        """The facet's values as `Term`s attributed to the researcher.

        `list_name` is `None` and stays `None`: an answer typed by a researcher is not a term
        from a controlled list, and R3.5 depends on the difference being visible. Recording it
        as a registry term would be the exact dishonesty §5.1 tier 2 exists to avoid.
        """
        return [
            Term(
                term=value,
                list_name=None,
                list_version=None,
                derivation=Derivation.RESEARCHER_ANSWER,
            )
            for value in self.values_for(facet)
        ]

    def single(self, facet: IntakeFacet) -> str | None:
        """The first value for a facet, for the fields that hold only one."""
        values = self.values_for(facet)
        return values[0] if values else None


class InterruptRequest(Frozen):
    """What the graph hands out when it pauses to ask.

    Returned to the caller of `run_pipeline` and passed through `interrupt()`, so it must stay
    plainly serialisable — anything clever here ends up in a checkpoint.
    """

    run_id: str
    asked_at: str
    intake_version: str
    questions: list[Question] = Field(default_factory=list)
