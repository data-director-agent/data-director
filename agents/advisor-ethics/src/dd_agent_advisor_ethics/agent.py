"""advisor.ethics: the Research Ethics Adviser persona (docs/specs/agents.md). A model-backed alpha.

Serves `governance.sensitive-data-identify` and `governance.embargo`. It flags fields whose names
suggest sensitive data and asks the questions a person must answer before sharing. It never
decides how sensitive data is treated and never suggests anonymisation (C2):
`governance.sensitive-data-handle` is left to people.

The keyword table (`keywords.yaml`) flags each field whose name contains one of its words. A
reader (`reader.py`) may then add flags and questions: by default it adds none, and with
`DD_ETHICS_READER=model` a model reads the names (`factory.py`). The merge is union only: every
keyword flag is kept, and a model may add a flag but never remove or re-categorise one, because a
missed field is the costlier mistake. Each flag and question records how it came about
(`derivation`). The adviser reads no data values and cites only its input, so its grounding mode
is `input_only`. The full persona, with policy records as a source and an evaluation set, is
TODO(#700).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from dd_agent_advisor_ethics.classes import (
    SensitivityContext,
    SensitivityFlag,
    SensitivityFlags,
    SensitivityQuestion,
)
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
)
KEYWORD_LIMITATION = (
    "No model is configured, so it matches field names against a short keyword list and misses "
    "abbreviations and names it does not list."
)
MODEL_LIMITATION = (
    "A model reads the field names as well as the keyword list; it may add flags but never removes "
    "one. The field names are sent to that model, and a hosted model is outside the institution. "
    "The profile's rule on what may go to a hosted model does not cover this input (TODO(#40)); a "
    "local model is the alternative (TODO(#39))."
)
PEOPLE_QUESTION = (
    "The data involve people. Confirm that ethics approval and participants' consent cover "
    "sharing them, with your institution's ethics and data protection staff."
)
EMBARGO_QUESTION = (
    "You intend an embargo. Confirm its length and reason against your funder's and journal's "
    "policies before deposit."
)
UNKNOWN_EMBARGO_QUESTION = "Say whether the data need an embargo before they are shared."


def load_keywords(path: Path = KEYWORDS) -> dict[str, list[str]]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return {str(category): [str(k).lower() for k in words] for category, words in table.items()}


class EthicsAdviser:
    spec = AgentSpec(
        agent_id="advisor.ethics",
        version="0.1.0a1",
        title="Research Ethics Adviser",
        icon="🧭",
        description=(
            "Flags fields whose names suggest personal or otherwise sensitive data, by keyword "
            "and, where one is configured, with a model that may add flags but never remove one. "
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
        if not context.fields and context.involves_people is None:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Give the dataset's field names, or say whether it involves people.",
            )

        lexical = [flag for name in context.fields if (flag := self._flag(name)) is not None]
        reading = self.reader.read(
            context, list(self.keywords), [flag.field for flag in lexical], ctx
        )
        # Union only: the keyword flags are kept as they are, and the reader's are added after.
        flags = lexical + [
            SensitivityFlag(
                field=added.field,
                category=added.category,
                reason=added.reason,
                derivation=Derivation.MODEL,
            )
            for added in reading.flags
        ]
        questions = [
            SensitivityQuestion(text=text, derivation=Derivation.TEMPLATE)
            for text in self._questions(context, flagged=bool(flags))
        ] + [
            SensitivityQuestion(text=text, derivation=Derivation.MODEL)
            for text in reading.questions
        ]
        limitations = [
            *LIMITATIONS,
            KEYWORD_LIMITATION if self.reader.model_id is None else MODEL_LIMITATION,
        ]

        ref = input_ref(ctx)
        calls = reading.calls
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"{len(flags)} of {len(context.fields)} field names suggest sensitive data: "
                    f"{len(lexical)} by keyword. {_how_read(reading)} A person must review every "
                    "field before sharing."
                ),
            ),
            payload=SensitivityFlags(
                flags=flags,
                questions=questions,
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

    def _questions(self, context: SensitivityContext, *, flagged: bool) -> list[str]:
        questions = []
        if context.involves_people or flagged:
            questions.append(PEOPLE_QUESTION)
        if context.embargo_intended:
            questions.append(EMBARGO_QUESTION)
        elif context.embargo_intended is None:
            questions.append(UNKNOWN_EMBARGO_QUESTION)
        return questions

    def _flag(self, name: str) -> SensitivityFlag | None:
        words = set(WORD.findall(name.lower()))
        for category, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword in words:
                    return SensitivityFlag(
                        field=name,
                        category=category,
                        matched=keyword,
                        derivation=Derivation.LEXICAL,
                    )
        return None


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
