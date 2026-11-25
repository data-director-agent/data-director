"""advisor.ethics: the Research Ethics Adviser persona (docs/specs/agents.md). A model-backed alpha.

Serves `governance.sensitive-data-identify` and `governance.embargo`. It flags fields whose names
suggest sensitive data and asks the questions a person must answer before sharing. In a project
it is given the project's inventory too, and checks its field, file and folder names and carries
over what the inventory's personal data detector found (`names.py`, #1540). It never
decides how sensitive data is treated and never suggests anonymisation (C2):
`governance.sensitive-data-handle` is left to people.

The keyword table (`keywords.yaml`) flags each field whose name contains one of its words. A
reader (`reader.py`) may then add flags and questions: by default a model reads the names, and
with `DD_ETHICS_READER=template` it adds none (`factory.py`). The merge is union only: every
keyword flag is kept, and a model may add a flag but never remove or re-categorise one, because a
missed field is the costlier mistake. Each flag and question records how it came about
(`derivation`). The adviser reads no data values and cites only its input, so its grounding mode
is `input_only`. A question about consent names the data use conditions of the GA4GH Data Use
Ontology (DUO) to check consent against, from `dd_duo`'s pinned release: packaged vocabulary,
like the keyword table, not a record retrieved for this run. It lists them and chooses none. The
full persona, with policy records as a source and an evaluation set, is TODO(#700).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import dd_duo
from dd_agent_advisor_ethics.classes import (
    DataUseTerm,
    SensitivityContext,
    SensitivityFlag,
    SensitivityFlags,
    SensitivityQuestion,
)
from dd_agent_advisor_ethics.names import Names, findings, free_text, names_of
from dd_agent_advisor_ethics.reader import Reader, Reading, TemplateReader
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    abstain,
    input_evidence,
    input_ref,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.inventory import FileInventory, PersonalDataFinding
from dd_sdk.contract.models import (
    Derivation,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)

KEYWORDS = Path(__file__).with_name("keywords.yaml")
WORD = re.compile(r"[a-z]+")

LIMITATIONS = (
    "It reads field names, never data values: a field it does not flag may still hold sensitive "
    "data.",
    "It does not check free text, images, audio or combinations of fields that identify people.",
    "It is an alpha with no evaluation set yet: how many sensitive fields it misses is not "
    "measured.",
    "It names data use conditions from the GA4GH Data Use Ontology for consent to be checked "
    "against; it does not know what participants agreed to, and chooses none of them.",
)
KEYWORD_LIMITATION = (
    "No model is configured, so it matches field names against a short keyword list and misses "
    "abbreviations and names it does not list."
)
MODEL_LIMITATION = (
    "A model reads the names as well as the keyword list; it may add flags but never removes one. "
    "The names are sent to that model, and a hosted model is outside the institution. The "
    "profile's rule on what may go to a hosted model covers names from the project's inventory, "
    "not names typed in (TODO(#40)); a local model is the alternative (TODO(#39))."
)
NO_INVENTORY_LIMITATION = (
    "It was given no inventory of the dataset's files, so it checked only the names it was "
    "given. An inventory made with dd-inventory, or Make inventory in the project, gives every "
    "table's field names and checks sampled values and small text files for personal data."
)
NO_DETECTOR_LIMITATION = (
    "The inventory was made without its personal data detector, so no data values or text files "
    "were checked."
)
DETECTOR_LIMITATION = (
    "The inventory's personal data detector checked sampled values, names and small text files "
    "on the researcher's computer. It finds patterns such as email addresses and NHS numbers, "
    "not every kind of personal data: a file it found nothing in may still hold some."
)
FINDINGS_QUESTION = (
    "The inventory's personal data detector found what may be personal data ({kinds}). Review "
    "each finding with your institution's ethics and data protection staff before sharing."
)
FREE_TEXT_QUESTION = (
    "These files' names suggest free text, which often names people: {paths}. Read them before "
    "they are shared."
)
# How many paths a question names before it says how many more there are.
MAX_PATHS = 5
PEOPLE_QUESTION = (
    "The data involve people. Confirm that ethics approval and participants' consent cover "
    "sharing them, and which of the data use conditions listed consent allows, with your "
    "institution's ethics and data protection staff."
)
EMBARGO_QUESTION = (
    "You intend an embargo. Confirm its length and reason against your funder's and journal's "
    "policies before deposit."
)
UNKNOWN_EMBARGO_QUESTION = "Say whether the data need an embargo before they are shared."
NOT_PEOPLE_QUESTION = (
    "You said the data do not involve people, but some field names suggest personal data. "
    "Confirm with your institution's ethics and data protection staff whether they do and, if "
    "so, which of the data use conditions listed consent allows, before sharing them."
)
# The DUO conditions a consent question lists (dd_duo): every permission, and the modifiers that
# consent forms most often state. Each must be a current term of the pinned release.
CONSENT_MODIFIERS = (
    "DUO:0000021",  # IRB, ethics approval required
    "DUO:0000046",  # NCU, non-commercial use only
    "DUO:0000019",  # PUB, publication required
    "DUO:0000026",  # US, user specific restriction
    "DUO:0000022",  # GS, geographical restriction
    "DUO:0000025",  # TS, time limit on use
)
LOCATION_QUESTION = (
    "Some fields hold locations. Confirm whether publishing them could expose people, private "
    "land or protected species, and at what precision they may be shared, before sharing them."
)
# The keyword category that marks a place, not a person (keywords.yaml).
LOCATION = "location"


def load_keywords(path: Path = KEYWORDS) -> dict[str, list[str]]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return {str(category): [str(k).lower() for k in words] for category, words in table.items()}


class EthicsAdviser:
    spec = AgentSpec(
        agent_id="advisor.ethics",
        version="0.1.0a3",
        title="Research Ethics Adviser",
        icon="🧭",
        description=(
            "Flags fields whose names suggest personal or otherwise sensitive data, by keyword "
            "and, where one is configured, with a model that may add flags but never remove one. "
            "In a project it reads the inventory's field, file and folder names and its personal "
            "data findings. "
            "Asks what must be confirmed about consent, ethics approval and embargo before "
            "sharing. Never decides how sensitive data is treated."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(SensitivityContext),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(SensitivityFlags),
        derivations={
            "flags.category": Derived(Derivation.MODEL, recorded_in="derivation"),
            "flags.matched": Derived(Derivation.LEXICAL),
            "flags.reason": Derived(Derivation.MODEL, recorded_in="derivation"),
            "questions.text": Derived(Derivation.MODEL, recorded_in="derivation"),
            "questions.data_use_terms": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
            "dropped": Derived(Derivation.TEMPLATE),
        },
        serves=("governance.sensitive-data-identify", "governance.embargo"),
    )

    def __init__(
        self, keywords: dict[str, list[str]] | None = None, reader: Reader | None = None
    ) -> None:
        self.keywords = keywords if keywords is not None else load_keywords()
        self.reader: Reader = reader if reader is not None else TemplateReader()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, SensitivityContext)  # the conductor checked spec.accepts
        inventory = context.project_file_inventory
        if not context.fields and context.involves_people is None and inventory is None:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Add an inventory of the dataset's files to the project, give the dataset's "
                "field names, or say whether it involves people.",
            )

        checked = names_of(context)
        found = findings(inventory)
        lexical = [
            flag for name in checked.names if (flag := self._flag(name, checked)) is not None
        ]
        reading = self.reader.read(
            context, checked.names, list(self.keywords), [flag.field for flag in lexical], ctx
        )
        # Union only: the keyword flags are kept as they are, and the reader's are added after.
        flags = lexical + [
            SensitivityFlag(
                field=added.field,
                category=added.category,
                files=list(checked.where.get(added.field, ())),
                reason=added.reason,
                derivation=Derivation.MODEL,
            )
            for added in reading.flags
        ]
        questions = [
            _template_question(text)
            for text in _questions(context, {flag.category for flag in flags})
            + _inventory_questions(context, found)
        ] + [
            SensitivityQuestion(text=text, derivation=Derivation.MODEL)
            for text in reading.questions
        ]
        limitations = [
            *LIMITATIONS,
            KEYWORD_LIMITATION if self.reader.model_id is None else MODEL_LIMITATION,
            _inventory_limitation(context, found),
        ]

        ref = input_ref(ctx)
        calls = reading.calls
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"{len(flags)} of {_count(len(checked.names), 'name')}{_from(checked)} "
                    f"suggest sensitive data: {len(lexical)} by keyword. {_how_read(reading)}"
                    f"{_detected(inventory, found)} A person must review every field before "
                    "sharing."
                ),
            ),
            payload=SensitivityFlags(
                flags=flags,
                questions=questions,
                inventory_findings=found,
                limitations=limitations,
                dropped=list(reading.dropped),
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
            model_id=reading.model_id,
            input_tokens=reading.usage.input_tokens,
            output_tokens=reading.usage.output_tokens,
            model_calls=calls.calls if calls is not None else (),
            prompts=calls.prompts if calls is not None else {},
        )

    def _flag(self, name: str, checked: Names | None = None) -> SensitivityFlag | None:
        words = set(WORD.findall(name.lower()))
        for category, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword in words:
                    return SensitivityFlag(
                        field=name,
                        category=category,
                        files=list(checked.where.get(name, ())) if checked else [],
                        matched=keyword,
                        derivation=Derivation.LEXICAL,
                    )
        return None


def _questions(context: SensitivityContext, categories: set[str]) -> list[str]:
    """The template questions: about people only when the researcher says the data involve
    people or a flag suggests it, worded so as not to contradict a researcher who said they do
    not (#1069); about locations when a location is flagged and people are not in question."""
    questions = []
    about_people = categories - {LOCATION}
    if context.involves_people:
        questions.append(PEOPLE_QUESTION)
    elif about_people:
        questions.append(
            NOT_PEOPLE_QUESTION if context.involves_people is False else PEOPLE_QUESTION
        )
    if LOCATION in categories and not context.involves_people and not about_people:
        questions.append(LOCATION_QUESTION)
    if context.embargo_intended:
        questions.append(EMBARGO_QUESTION)
    elif context.embargo_intended is None:
        questions.append(UNKNOWN_EMBARGO_QUESTION)
    return questions


def consent_terms() -> list[DataUseTerm]:
    """The DUO conditions a consent question lists, from the pinned release."""
    chosen = [*dd_duo.terms("permission"), *map(dd_duo.lookup, CONSENT_MODIFIERS)]
    return [
        DataUseTerm(
            term_id=term.id,
            shorthand=term.shorthand,
            term_label=term.label,
            term_kind=term.kind,
            term_iri=term.url,
        )
        for term in chosen
        if term is not None
    ]


def _template_question(text: str) -> SensitivityQuestion:
    """A question from the template; one about consent lists the DUO conditions."""
    about_consent = text in (PEOPLE_QUESTION, NOT_PEOPLE_QUESTION)
    return SensitivityQuestion(
        text=text,
        derivation=Derivation.TEMPLATE,
        data_use_terms=consent_terms() if about_consent else [],
    )


def _inventory_questions(
    context: SensitivityContext, found: list[PersonalDataFinding] | None
) -> list[str]:
    """The questions the inventory raises: what its detector found, and the files whose names
    suggest free text, which the adviser cannot read."""
    questions = []
    if found:
        kinds = ", ".join(sorted({str(f.finding_kind) for f in found}))
        questions.append(FINDINGS_QUESTION.format(kinds=kinds))
    if texts := free_text(context.project_file_inventory):
        named = ", ".join(texts[:MAX_PATHS])
        if len(texts) > MAX_PATHS:
            named += f" and {len(texts) - MAX_PATHS} more"
        questions.append(FREE_TEXT_QUESTION.format(paths=named))
    return questions


def _inventory_limitation(
    context: SensitivityContext, found: list[PersonalDataFinding] | None
) -> str:
    if context.project_file_inventory is None:
        return NO_INVENTORY_LIMITATION
    return NO_DETECTOR_LIMITATION if found is None else DETECTOR_LIMITATION


def _from(checked: Names) -> str:
    """Where the names came from, when the inventory gave any."""
    if not checked.from_inventory:
        return ""
    return f" ({checked.from_inventory} from the project's inventory)"


def _detected(inventory: FileInventory | None, found: list[PersonalDataFinding] | None) -> str:
    """What the statement says of the inventory's personal data detector."""
    if inventory is None:
        return ""
    if found is None:
        return " The inventory was made without its personal data detector."
    if not found:
        return (
            " The inventory's personal data detector found nothing, which does not mean the "
            "data hold none."
        )
    return (
        f" The inventory's personal data detector made {_count(len(found), 'finding')}, "
        "carried over as they are."
    )


def _how_read(reading: Reading) -> str:
    """What the statement says about the reader: whether a model read the names, what it added,
    and what was not used."""
    if reading.model_id is None:
        return "No model is configured, so the field names were matched by keyword only."
    if reading.unused:
        return (
            f"The field names were matched by keyword only, because {reading.unused} "
            f"({reading.model_id})."
        )
    said = (
        f"A model ({reading.model_id}) added {_count(len(reading.flags), 'flag')} and "
        f"{_count(len(reading.questions), 'question')}"
    )
    if reading.dropped:
        said += (
            f"; {_count(len(reading.dropped), 'item')} it returned "
            f"{'was' if len(reading.dropped) == 1 else 'were'} not used ("
            + "; ".join(reading.dropped)
            + ")"
        )
    return said + "."


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"
