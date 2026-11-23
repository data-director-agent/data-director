"""Describing a project before its data are collected (`setup.project`, docs/specs/projects.md).

Phase 1 opens by finding out what the project is and the data it will produce, since every later
planning step builds on it: the README plan, the standards, storage, formats and the Data
Management Plan. The Planner proposes each as a project fact for the researcher to confirm or
correct: a `project_summary`, a `field_of_study`, a `project_period`, and a `planned_data` fact for
each output. Nothing counts until a person decides it (invariant 28).

A fact comes from what the researcher said, which the orchestrator passes on in the request
(`ProjectDescriptionRequest`), or else from a document they attached, such as a proposal or an
award letter. A document is read only by a model (`ModelDescriber`), whose reply is constrained to
a schema (`DescribeReply`); each thing it finds must quote the document it names, and is dropped
and said otherwise (`read_plan.unquoted`), as a plan's commitments are. `TemplateDescriber` reads
nothing. A fact a person has already decided is never proposed again, and what is still unknown
is said in `still_needed`, for the orchestrator to ask.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from dd_agent_advisor_dmp.classes import DmpDiscrepancies, ProjectDescriptionRequest
from dd_agent_advisor_dmp.match import model_use
from dd_agent_advisor_dmp.read_plan import DocumentModel, _Reply, unquoted
from dd_sdk.agent import AgentResult, RunContext, input_evidence, input_ref
from dd_sdk.contract.facts import (
    PARTIAL_DATE_PATTERN,
    PLAN_SUBJECT,
    FactKind,
    ProjectDocument,
    ProjectFact,
)
from dd_sdk.contract.models import Outcome, OutcomeStatus
from dd_sdk.model import Usage
from dd_sdk.prompts import ModelCallLog

DESCRIBE_PROMPT = Path(__file__).with_name("describe_prompt.md").read_text(encoding="utf-8").strip()
SAID = "You said this in the conversation; confirm or correct it."
LIMITATIONS = (
    "It proposes what the project is and the data it will produce from what you said and the "
    "documents you attached; each counts only once you confirm or correct it on the project page.",
    "A model's reading of a document may be wrong or miss something: check each proposal against "
    "its quoted passage. Only a quote found in the document is used, which does not make the "
    "reading right.",
    "It does not say what the project should collect, nor judge the research design.",
    "Its reading of documents has no evaluation set yet: how often the model misreads a proposal "
    "is not measured.",
)
# What each kind describes, as `still_needed` names it while no one has given it.
NEEDED = {
    FactKind.PROJECT_SUMMARY: "what the project is for: its aims and questions",
    FactKind.PLANNED_DATA: "the data it will produce, and how they will be collected",
    FactKind.FIELD_OF_STUDY: "its field of study",
    FactKind.PROJECT_PERIOD: "when it starts and ends",
}


class Quoted(_Reply):
    document: int
    quote: str


class ReadSummary(Quoted):
    text: str


class ReadField(Quoted):
    name: str


class ReadPeriod(Quoted):
    start: str
    end: str | None


class ReadOutput(Quoted):
    output: str
    description: str
    collection_method: str | None
    formats: str | None
    volume: str | None


class DescribeReply(_Reply):
    """What the model replies with. Every field is required, as a provider's strict schema needs."""

    summary: ReadSummary | None
    field_of_study: ReadField | None
    period: ReadPeriod | None
    outputs: list[ReadOutput]


@dataclass(frozen=True)
class Description:
    """What a describer read from the attached documents and the checks kept."""

    proposals: tuple[ProjectFact, ...] = ()
    dropped: tuple[str, ...] = ()
    unused: str | None = None
    model_id: str | None = None
    read: tuple[str, ...] = ()
    cut: tuple[str, ...] = ()
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None


class Describer(Protocol):
    model_id: str | None

    def read(self, documents: Sequence[ProjectDocument], ctx: RunContext) -> Description: ...


class TemplateDescriber:
    """Reads nothing: a document's text is read only by a model."""

    model_id: str | None = None

    def read(self, documents: Sequence[ProjectDocument], ctx: RunContext) -> Description:
        return Description()


class ModelDescriber(DocumentModel):
    """Reads what the attached documents say of the project."""

    def read(self, documents: Sequence[ProjectDocument], ctx: RunContext) -> Description:
        got, given, cut = self.asked(documents, ctx, DESCRIBE_PROMPT, DescribeReply)
        if got.parsed is None:
            return Description(
                unused=got.why,
                model_id=got.model_id,
                read=got.names,
                usage=got.usage,
                calls=got.calls,
            )
        proposals, dropped = check(got.parsed, given)
        return Description(
            proposals=proposals,
            dropped=dropped,
            model_id=got.model_id,
            read=got.names,
            cut=tuple(sorted(cut)),
            usage=got.usage,
            calls=got.calls,
        )


def check(
    reply: DescribeReply, documents: Sequence[ProjectDocument]
) -> tuple[tuple[ProjectFact, ...], tuple[str, ...]]:
    """The facts of a reply that may be proposed, and why any others were not."""
    found: list[tuple[str, Quoted, ProjectFact | str]] = []
    if reply.summary is not None:
        found.append(("the summary", reply.summary, _summary(reply.summary.text)))
    if reply.field_of_study is not None:
        found.append(("the field of study", reply.field_of_study, _field(reply.field_of_study)))
    if reply.period is not None:
        found.append(("the period", reply.period, _period(reply.period)))
    found += [(o.output.strip() or "an output", o, _output(o)) for o in reply.outputs]
    kept: list[ProjectFact] = []
    dropped: list[str] = []
    for what, quoted, fact in found:
        why = (
            fact
            if isinstance(fact, str)
            else unquoted(quoted.document, quoted.quote, documents, what)
        )
        if why is not None:
            dropped.append(f"{what}: {why}")
            continue
        assert isinstance(fact, ProjectFact)
        name = documents[quoted.document - 1].documentation_name
        passage = " ".join(quoted.quote.split())
        because = f'Read from {name}: "{passage}" Check it against the passage.'
        kept.append(fact.model_copy(update={"proposed_because": because}))
    return tuple(kept), tuple(dropped)


def _summary(text: str) -> ProjectFact | str:
    if not text.strip():
        return "it says nothing"
    return ProjectFact(
        fact_kind=FactKind.PROJECT_SUMMARY, fact_subject=PLAN_SUBJECT, summary_text=text.strip()
    )


def _field(read: ReadField) -> ProjectFact | str:
    if not read.name.strip():
        return "it names no field"
    return ProjectFact(
        fact_kind=FactKind.FIELD_OF_STUDY, fact_subject=PLAN_SUBJECT, field_name=read.name.strip()
    )


def _period(read: ReadPeriod) -> ProjectFact | str:
    dates = [d for d in (read.start, read.end) if d is not None]
    if not all(re.fullmatch(PARTIAL_DATE_PATTERN, d) for d in dates):
        return "a date is not a year, a month or a day"
    return ProjectFact(
        fact_kind=FactKind.PROJECT_PERIOD,
        fact_subject=PLAN_SUBJECT,
        period_start=read.start,
        period_end=read.end,
    )


def _output(read: ReadOutput) -> ProjectFact | str:
    if not read.output.strip() or not read.description.strip():
        return "it names or describes no output"
    return ProjectFact(
        fact_kind=FactKind.PLANNED_DATA,
        fact_subject=read.output.strip(),
        planned_description=read.description.strip(),
        planned_collection_method=_value(read.collection_method),
        planned_format=_value(read.formats),
        planned_volume=_value(read.volume),
    )


def _value(text: str | None) -> str | None:
    return " ".join(text.split()) if text and text.strip() else None


def said(asked: ProjectDescriptionRequest) -> list[ProjectFact]:
    """The facts the researcher gave in the conversation, as the orchestrator passed them on."""
    facts: list[ProjectFact] = []
    if asked.research_summary and asked.research_summary.strip():
        facts.append(
            ProjectFact(
                fact_kind=FactKind.PROJECT_SUMMARY,
                fact_subject=PLAN_SUBJECT,
                summary_text=asked.research_summary.strip(),
            )
        )
    if asked.field_of_study and asked.field_of_study.strip():
        facts.append(
            ProjectFact(
                fact_kind=FactKind.FIELD_OF_STUDY,
                fact_subject=PLAN_SUBJECT,
                field_name=asked.field_of_study.strip(),
            )
        )
    if asked.period_start:
        facts.append(
            ProjectFact(
                fact_kind=FactKind.PROJECT_PERIOD,
                fact_subject=PLAN_SUBJECT,
                period_start=asked.period_start,
                period_end=asked.period_end,
            )
        )
    facts += [
        ProjectFact(
            fact_kind=FactKind.PLANNED_DATA,
            fact_subject=o.output.strip(),
            planned_description=o.output_description.strip(),
            planned_collection_method=_value(o.collection_method),
            planned_format=_value(o.formats),
            planned_volume=_value(o.volume),
        )
        for o in asked.expected_outputs
        if o.output.strip() and o.output_description.strip()
    ]
    return [f.model_copy(update={"proposed_because": SAID}) for f in facts]


def proposed(asked: ProjectDescriptionRequest, read: Sequence[ProjectFact]) -> list[ProjectFact]:
    """What to propose: what the researcher said, then what was read of what they did not say,
    leaving out whatever a person has already decided."""
    decided = {_key(f) for f in asked.project_decisions}
    given = said(asked)
    kinds = {f.fact_kind for f in given if f.fact_kind != FactKind.PLANNED_DATA}
    keys = {_key(f) for f in given}
    from_documents = [f for f in read if f.fact_kind not in kinds and _key(f) not in keys]
    return [f for f in [*given, *from_documents] if _key(f) not in decided]


def still_needed(asked: ProjectDescriptionRequest, proposals: Sequence[ProjectFact]) -> list[str]:
    """What neither a decision nor a proposal gives, in `NEEDED`'s order."""
    held = {f.fact_kind for f in [*asked.project_decisions, *proposals]}
    return [what for kind, what in NEEDED.items() if kind not in held]


def _key(fact: ProjectFact) -> tuple[FactKind, str]:
    return fact.fact_kind, fact.fact_subject.casefold()


def describe(
    asked: ProjectDescriptionRequest, describer: Describer, ctx: RunContext
) -> AgentResult:
    """The project's description, proposed as facts, with what is still needed."""
    documents = asked.project_documents
    read = describer.read(documents, ctx) if documents else Description()
    proposals = proposed(asked, read.proposals)
    needed = still_needed(asked, proposals)
    return AgentResult(
        outcome=Outcome(
            status=OutcomeStatus.SUCCEEDED,
            statement=statement(proposals, needed, read, attached=bool(documents)),
        ),
        payload=DmpDiscrepancies(
            proposed_facts=proposals,
            still_needed=needed,
            dropped=list(read.dropped),
            limitations=list(LIMITATIONS),
            grounded_on=[input_ref(ctx)],
        ),
        evidence=[input_evidence(ctx)],
        **model_use(read.model_id if read.calls else None, read.usage, read.calls),
    )


def statement(
    proposals: Sequence[ProjectFact], needed: Sequence[str], read: Description, *, attached: bool
) -> str:
    """What the outcome says: what is proposed and from where, and what is still needed."""
    count = len(proposals)
    said = (
        f"It proposes {count} fact{'' if count == 1 else 's'} about the project for you to "
        "confirm, correct or reject on the project page."
        if proposals
        else "It proposes nothing new about the project."
    )
    names = ", ".join(read.read) or "the attached documents"
    if read.unused:
        said += f" It could not read {names}, because {read.unused} ({read.model_id})."
    elif read.model_id is not None:
        said += f" A model ({read.model_id}) read {names}, quoting the passage for each."
    elif attached:
        said += " Documents are attached, but reading them needs a model, and none is configured."
    if read.cut:
        said += f" Only the start of {', '.join(read.cut)} was read, for room."
    if read.dropped:
        said += f" {len(read.dropped)} reading(s) were not used: " + "; ".join(read.dropped) + "."
    if needed:
        said += " Still needed: " + "; ".join(needed) + "."
    return said
