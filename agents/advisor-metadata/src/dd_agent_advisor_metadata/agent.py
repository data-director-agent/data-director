"""advisor.metadata: the Metadata Librarian persona (docs/specs/agents.md), a model-backed alpha,
and the drafter of the project's metadata record (#200, #698).

Serves `preparation.metadata-standard` and `preparation.metadata` (R2). Given a `DraftRequest` for
a `metadata_record`, it drafts a project document (docs/specs/projects.md): a record in the
standard the chosen repository's requirements follow, as that standard's registered definition
writes it (docs/specs/metadata-standards.md), with `conforms_to` set to the repository's
(docs/specs/deposit.md). Every property the repository's requirements list is written, with its
qualifier, and its value left as a gap for the researcher. The librarian fills only what holds
for any deposit, that the resource is a dataset, what the inventory states, the files' formats
and sizes, and what the project's researchers kept from their public ORCID records
(docs/specs/projects.md): each researcher as a creator, with their iD and current employers,
their keywords as subjects, and
their grants as funding references, wherever the repository asks for those properties.

Each value it leaves null is a gap with a question (`questions.py`), and an answer the researcher
recorded to it is placed as given (docs/specs/drafting.md). The question about the licence names
the licences the repository accepts, when its requirements list them. Where a model is configured
(`factory.py`), it suggests values for some questions, beside the question and never in the
record (`suggest.py`); the record's text is the rule's either way. Where the data were collected
is asked in two steps: whether the location may be published, and at what precision, and only
then the place (`location.py`, #1073). The question about the subjects names the vocabularies the
project chose for the dataset (`chosen.py`, #1391).

It reads how each property is written and what is asked about it from DataCite's definition in
`dd_metadata_records` (docs/specs/metadata-standards.md), which shared field a property gives from
`shares.yaml`, and writes the record through the definition's JSON codec. An entry the repository
asks for from a named subject classification, such as ORDA's categories from the ANZSRC Fields of
Research, is suggested only from that classification's fields, retrieved through the tool gateway,
and each suggestion cites the field's record (`categories.py`, #703). So its grounding mode is
`retrieval`: it records reading its input as a retrieval, and cites its input and each field's
record.
Keywords from other vocabularies are TODO(#956). Regenerating a record drafts it afresh, and names
the version it replaces in `revises`. It does not convert a record to another standard (R6): it
abstains with `capability_not_implemented` for requirements in a standard no registered definition
covers. Conversion through a shared pivot is TODO(#1363).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from dd_agent_advisor_metadata import categories, chosen, location, researchers, scope
from dd_agent_advisor_metadata.form import Drafting, drafting
from dd_agent_advisor_metadata.questions import (
    Gap,
    answers_by_question,
    ask,
    gaps,
    place,
)
from dd_agent_advisor_metadata.suggest import Ask, Suggester, Suggestions, TemplateSuggester
from dd_metadata_records import Standards, set_path
from dd_sdk import shared_answers
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    input_evidence,
    input_ref,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftRequest,
    FileInventory,
    GroundingMode,
    InvocationRequest,
    Obligation,
    Outcome,
    OutcomeStatus,
    RepositoryRequirements,
)
from dd_sdk.tools import ToolRecord
from dd_sdk.tracing import retrieval_span

SCHEMA: Final = "http://schema.org/"
# The pivot terms whose properties the librarian treats specially, whatever the standard calls
# them: the licence, whose question names the licences the repository accepts; the keywords,
# whose question names the vocabularies the project chose; and what it fills from the inventory
# and the requirements.
LICENCE: Final = SCHEMA + "license"
KEYWORDS: Final = SCHEMA + "keywords"
FORMATS: Final = SCHEMA + "encodingFormat"
SIZES: Final = SCHEMA + "contentSize"
SCHEMA_VERSION: Final = "http://schema.org/schemaVersion"

# What the librarian does not do, said in every outcome: its payload is the core Document, which
# has no room for a list of limitations (docs/specs/agents.md).
LIMITATIONS = (
    "It is an alpha: it fills no value that only you can give, beyond what you kept from your "
    "ORCID record and the answers you recorded; it suggests terms only from the subject "
    "classifications a repository names, and no keywords from other vocabularies; it maps "
    "nothing between schemas, does not check that a value is correct, and reads neither an "
    "earlier version nor the reason given for a decision on it."
)


@dataclass(frozen=True, slots=True)
class _Categories:
    """The records the categories suggested cite, and what the outcome says about them."""

    records: tuple[ToolRecord, ...] = ()
    sentence: str = ""


class MetadataLibrarian:
    spec = AgentSpec(
        agent_id="advisor.metadata",
        version="0.3.0a0",
        title="Metadata Librarian",
        icon="🏷️",
        description=(
            "Alpha. Drafts a project's metadata record in the standard the chosen repository's "
            "requirements follow, as its registered definition writes it, with every "
            "property the repository requires or recommends, filling only the resource "
            "type, the formats and sizes the file inventory gives, the creators, subjects and "
            "funding the researchers kept from their ORCID records, and the answers they "
            "recorded. It asks about every value it leaves empty, and where a model is "
            "configured suggests some, beside the question and never in the record: a category "
            "only from the classification the repository names, citing the field's record."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DraftRequest),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(Document),
        derivations={
            "document_title": Derived(Derivation.TEMPLATE),
            "document_text": Derived(Derivation.TEMPLATE),
            "document_questions": Derived(Derivation.TEMPLATE),
            "document_questions.suggested_answer": Derived(
                Derivation.MODEL, recorded_in="suggestion_derivation"
            ),
        },
        serves=("preparation.metadata-standard", "preparation.metadata"),
        tools=categories.USES,
    )

    def __init__(
        self, suggester: Suggester | None = None, standards: Standards | None = None
    ) -> None:
        self.suggester = suggester if suggester is not None else TemplateSuggester()
        # The standards it drafts in: the registered ones unless a test gives others.
        self.standards = standards

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DraftRequest)  # the conductor checked spec.accepts
        found_scope = scope.drafted(asked, self.standards)
        if isinstance(found_scope, AgentResult):
            return found_scope
        requirements, standard = found_scope
        draft = drafting(standard)

        # What the record is drafted from is the input: reading it is this run's first retrieval.
        with retrieval_span(ctx.tracer, ctx.input_ref, ctx.input_hash):
            record, filled = _record(draft, requirements, asked.inventory)
        filled += researchers.fill(record, asked.researchers, draft.definition)
        found = gaps(record, draft.definition.vocabulary_keys)
        open_gaps = place(record, found, answers_by_question(asked.draft_answers))
        pairs, withheld = _ask(draft, open_gaps, asked)
        pairs = _offer(pairs, asked)
        questions, suggested, cited = self._questions(
            draft, pairs, _facts(requirements, asked.inventory), ctx
        )
        required = sum(f.obligation == Obligation.REQUIRED for f in requirements.fields)
        statement = (
            f"A {draft.definition.name} record for {requirements.repository_name} with the "
            f"{len(requirements.fields)} properties it asks for ({required} required), drafted "
            f"by rule. Filled: {', '.join(filled) or 'nothing'}"
            f"{_placed(len(found) - len(open_gaps))}. It asks "
            f"{_count(len(questions), 'question')} about the values left null. "
            f"{''.join(s + ' ' for s in withheld)}{_how_suggested(suggested)}"
            f"{_spaced(cited.sentence)}"
            f"{shared_answers.how_offered(questions)}"
        )
        current = asked.current_version
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."

        ref = input_ref(ctx)
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=f"{statement} {LIMITATIONS}"),
            payload=Document(
                document_kind=DocumentKind.METADATA_RECORD,
                document_title=(current.document_title if current else None)
                or f"Metadata record for {requirements.repository_name}",
                media_type=draft.media_type,
                conforms_to=requirements.conforms_to,
                document_text=standard.write(record, draft.media_type),
                document_derivation=Derivation.TEMPLATE,
                revises=current.version_ref if current else None,
                document_questions=questions,
                grounded_on=[ref, *(r.ref() for r in cited.records)],
            ),
            evidence=[input_evidence(ctx), *(r.evidence() for r in cited.records)],
            model_id=suggested.model_id,
            input_tokens=suggested.usage.input_tokens,
            output_tokens=suggested.usage.output_tokens,
            model_calls=tuple(suggested.calls.calls) if suggested.calls else (),
            prompts=dict(suggested.calls.prompts) if suggested.calls else {},
        )

    def _questions(
        self,
        draft: Drafting,
        pairs: Sequence[tuple[Gap, DocumentQuestion]],
        facts: Mapping[str, Any],
        ctx: RunContext,
    ) -> tuple[list[DocumentQuestion], Suggestions, _Categories]:
        """The questions, with the suggester's value where it offered one. The suggester is
        given the facts the record is drafted from and the questions on properties the rule
        table lets it suggest, never an answer or an earlier version (docs/specs/drafting.md,
        invariant 7). An entry from a named classification is suggested only from the fields the
        gateway returned, and offered as the label of the field's own record, which it cites
        (`categories.py`)."""
        questions = [q for _, q in pairs]
        suggestable = [
            (gap, q)
            for gap, q in pairs
            if draft.form_of(gap.prop).suggest and q.suggested_answer is None
        ]
        named = [gap.vocabulary for gap, _ in suggestable if gap.vocabulary]
        offered = (
            categories.offer(ctx, named)
            if named and self.suggester.model_id is not None
            else categories.Offered()
        )
        asks = [
            Ask(
                q.question_id,
                gap.path,
                gap.prop,
                q.question_prompt,
                gap.qualifier,
                offered.choices.get(gap.vocabulary or "", ()),
            )
            for gap, q in suggestable
            if not gap.names_a_vocabulary or gap.vocabulary in offered.choices
        ]
        suggested = self.suggester.suggest(facts, asks, ctx) if asks else Suggestions()
        vocabulary = {q.question_id: gap.vocabulary for gap, q in suggestable}
        chosen = {
            a.question_id: (str(vocabulary[a.question_id]), suggested.answers[a.question_id])
            for a in asks
            if a.choices and a.question_id in suggested.answers
        }
        cited = categories.cite(ctx, chosen)
        answers = {
            **{q: v for q, v in suggested.answers.items() if q not in chosen},
            **cited.labels,
        }
        suggested = replace(
            suggested, answers=answers, dropped=(*suggested.dropped, *cited.dropped)
        )
        return (
            [
                q.model_copy(
                    update={"suggested_answer": value, "suggestion_derivation": Derivation.MODEL}
                )
                if (value := answers.get(q.question_id))
                else q
                for q in questions
            ],
            suggested,
            _Categories(cited.records, categories.sentence(offered, cited)),
        )


def _ask(
    draft: Drafting, open_gaps: Sequence[Gap], asked: DraftRequest
) -> tuple[list[tuple[Gap, DocumentQuestion]], list[str]]:
    """The question asked about each open gap, and a sentence for each value left null and
    not asked about because a person decided it is withheld. A value the rule table asks
    `publish` about is asked for only once a person decided it may be published
    (`location.py`)."""
    prompts = {prop: form.ask for prop, form in draft.form.items()}
    requirements = asked.requirements
    licence = draft.path_for(LICENCE)
    if licence is not None and requirements is not None and requirements.licences:
        # The researcher chooses among the licences the repository accepts, and learns of a
        # clash with a journal's or funder's licence before validation refuses the record.
        prompts[licence] = (
            f"{prompts.get(licence) or 'Under what licence is the dataset shared?'} "
            f"{requirements.repository_name} accepts: {', '.join(requirements.licences)}."
        )
    keywords = draft.path_for(KEYWORDS)
    if keywords is not None:
        prompts[keywords] = chosen.subjects_prompt(prompts.get(keywords), asked.project_decisions)
    answers = answers_by_question(asked.draft_answers)
    located = location.located_fields(asked.inventory)
    by_project = location.decided(asked.project_decisions, located)
    pairs: list[tuple[Gap, DocumentQuestion]] = []
    withheld: dict[str, None] = {}
    for gap in open_gaps:
        publish = draft.form_of(gap.prop).publish
        question = ask(gap, prompts).model_copy(update={"shared_field": draft.shared_field(gap)})
        if publish is None:
            pairs.append((gap, question))
            continue
        decision = by_project or location.answered(answers.get(location.asks_first(gap)))
        if decision is None:
            first = DocumentQuestion(
                question_id=location.asks_first(gap),
                question_prompt=location.first_question(located, publish),
                gap_property=location.entry_path(gap),
            )
            pairs.append((gap, first))
        elif decision.withheld:
            withheld[location.withheld_sentence(decision)] = None
        else:
            prompt = location.second_question(decision, question.question_prompt)
            pairs.append((gap, question.model_copy(update={"question_prompt": prompt})))
    return pairs, list(withheld)


def _record(
    draft: Drafting, requirements: RepositoryRequirements, inventory: FileInventory | None
) -> tuple[dict[str, Any], list[str]]:
    """The record's logical tree, with a gap (None) for every value left to give, and the
    properties filled by rule."""
    record: dict[str, Any] = {}
    filled: list[str] = []
    for field in requirements.fields:
        form = draft.form_of(field.property)
        *parents, last = field.property.split(".")
        node = record
        for part in parents:
            node = node.setdefault(part, {})
        if form.filled is not None:
            node[last] = form.filled
            filled.append(field.property)
        elif form.value is not None:
            entry = {form.value: None, **(field.qualifier or {})}
            node.setdefault(last, []).append(entry)
        else:
            node.setdefault(last, None)
    formats, sizes = draft.path_for(FORMATS), draft.path_for(SIZES)
    if inventory is not None and inventory.inventory_files:
        files = inventory.inventory_files
        types = sorted({f.file_media_type for f in files if f.file_media_type})
        total = sum(f.file_size for f in files)
        if formats is not None and types:
            set_path(record, formats, types)
            filled.append(formats)
        if sizes is not None:
            set_path(record, sizes, [f"{len(files)} files", f"{total} bytes"])
            filled.append(sizes)
    if (version := draft.path_for(SCHEMA_VERSION)) is not None:
        set_path(record, version, requirements.conforms_to)
    return record, filled


def _offer(
    pairs: Sequence[tuple[Gap, DocumentQuestion]], asked: DraftRequest
) -> list[tuple[Gap, DocumentQuestion]]:
    """Each question on a shared field offered the researcher's own answer to it in another
    document, or the fact people decided, before any model suggests (`dd_sdk.shared_answers`)."""
    offered = shared_answers.offer(
        [q for _, q in pairs], asked.shared_answers, asked.project_decisions
    )
    return [(gap, q) for (gap, _), q in zip(pairs, offered, strict=True)]


def _facts(requirements: RepositoryRequirements, inventory: FileInventory | None) -> dict[str, Any]:
    """What a suggester is given: the repository, the properties it asks for, and the inventory's
    structure. Never the data, a description a person wrote, the researchers' records or an
    answer (docs/specs/drafting.md, invariant 4)."""
    files = inventory.inventory_files if inventory is not None else []
    return {
        "repository": requirements.repository_name,
        "conforms_to": requirements.conforms_to,
        "properties": [
            {
                "property": f.property,
                "obligation": f.obligation.value,
                **({"qualifier": f.qualifier} if f.qualifier else {}),
            }
            for f in requirements.fields
        ],
        "files": [
            {
                "path": f.file_path,
                "media_type": f.file_media_type,
                "size": f.file_size,
                "fields": [
                    {"name": c.name, "type": c.field_type, "format": c.field_format}
                    for c in f.file_fields
                ],
            }
            for f in files
        ],
    }


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _spaced(sentence: str) -> str:
    return f" {sentence}" if sentence else ""


def _placed(n: int) -> str:
    return f", and {_count(n, 'answer')} you recorded" if n else ""


def _how_suggested(suggested: Suggestions) -> str:
    """The sentence saying whether a model suggested values, and what was not offered."""
    if suggested.model_id is None:
        return "No model suggested values."
    if suggested.unused is not None:
        return f"No suggestion is offered: {suggested.unused}."
    sentence = (
        f"A model suggested {_count(len(suggested.answers), 'value')}, offered beside its "
        "question and never written into the record."
    )
    if suggested.dropped:
        sentence += (
            f" {_count(len(suggested.dropped), 'suggestion')} not offered: "
            + "; ".join(suggested.dropped)
            + "."
        )
    return sentence


def build() -> MetadataLibrarian:
    """The librarian with no model; `factory.build` reads the agent's settings."""
    return MetadataLibrarian()
