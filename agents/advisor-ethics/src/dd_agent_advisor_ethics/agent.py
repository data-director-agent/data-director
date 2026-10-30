"""advisor.ethics: the Research Ethics Adviser persona (ADR-0033). A mock.

Serves `governance.sensitive-data-identify` and `governance.embargo`. It flags fields whose names
suggest sensitive data and asks the questions a person must answer before sharing. It never
decides how sensitive data is treated and never suggests anonymisation (C2):
`governance.sensitive-data-handle` is left to people.

The mock matches field names against `keywords.yaml`. It reads no data values, consults no source
and calls no model, so its grounding mode is `none` and it cites only its input. The real adviser
is TODO(#355).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dd_agent_advisor_ethics.classes import SensitivityContext, SensitivityFlag, SensitivityFlags
from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

KEYWORDS = Path(__file__).with_name("keywords.yaml")
WORD = re.compile(r"[a-z]+")

LIMITATIONS = (
    "This is a mock: it matches field names against a short keyword list and reads no data values.",
    "A field it does not flag may still hold sensitive data.",
    "It does not check free text, images, audio or combinations of fields that identify people.",
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
        description=(
            "Mock. Flags fields whose names suggest personal or otherwise sensitive data, and asks "
            "what must be confirmed about consent, ethics approval and embargo before sharing. "
            "Never decides how sensitive data is treated."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(SensitivityContext),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(SensitivityFlags),
        derivations={
            "flags.category": Derived(Derivation.LEXICAL),
            "flags.matched": Derived(Derivation.LEXICAL),
            "questions": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("governance.sensitive-data-identify", "governance.embargo"),
    )

    def __init__(self, keywords: dict[str, list[str]] | None = None) -> None:
        self.keywords = keywords if keywords is not None else load_keywords()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, SensitivityContext)  # the conductor checked spec.accepts
        if not context.fields and context.involves_people is None:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="Give the dataset's field names, or say whether it involves people.",
                )
            )

        flags = [flag for name in context.fields if (flag := self._flag(name)) is not None]
        questions = []
        if context.involves_people or flags:
            questions.append(PEOPLE_QUESTION)
        if context.embargo_intended:
            questions.append(EMBARGO_QUESTION)
        elif context.embargo_intended is None:
            questions.append(UNKNOWN_EMBARGO_QUESTION)

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: {len(flags)} of {len(context.fields)} field names suggest sensitive "
                    "data. A person must review every field before sharing."
                ),
            ),
            payload=SensitivityFlags(
                flags=flags,
                questions=questions,
                limitations=list(LIMITATIONS),
                grounded_on=[ref],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
        )

    def _flag(self, name: str) -> SensitivityFlag | None:
        words = set(WORD.findall(name.lower()))
        for category, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword in words:
                    return SensitivityFlag(field=name, category=category, matched=keyword)
        return None


def build() -> EthicsAdviser:
    return EthicsAdviser()


def main() -> int:
    """The `dd-advisor-ethics` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
