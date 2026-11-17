"""advisor.rights: the Rights and Licensing Adviser persona (docs/specs/agents.md). An alpha.

Serves `deposit.licence` and `deposit.access`. It lists data licences that fit the reuse the
researcher wants to allow, and the access levels with when each applies, and asks the questions
a person must answer first. The researcher chooses: it never picks a licence or an access level.

Rules first (the deterministic shell): its options come from `licences.yaml`. A reuse wanted that
is one of the table's values selects the licences that fit it; a mandated licence is the only one
listed; the access levels and the fixed questions follow from what the researcher said. What the
rules cannot read goes to an interpreter (`interpret.py`). With a model configured
(`DD_RIGHTS_INTERPRETER`, `factory.py`), the model may read a reuse wish in the researcher's own
words as the table's values, order the licences that fit, and add questions about third-party
content or a mandate. It chooses only from the table: a licence it names from outside is dropped
and recorded. Each licence and question records how it came about in `derivation`.

It reads only its input, so its grounding mode is `input_only` and it cites only its input.
Drawing licences from the SPDX licence list through the tool gateway is TODO(#877); the
repository's own licence options and an evaluation set are TODO(#702).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_rights.classes import (
    AccessOption,
    LicenceOption,
    RightsContext,
    RightsOptions,
    RightsQuestion,
)
from dd_agent_advisor_rights.interpret import (
    Asked,
    Interpreter,
    Reading,
    TemplateInterpreter,
    key,
)
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

LICENCES = Path(__file__).with_name("licences.yaml")
SPDX_URL = "https://spdx.org/licenses/{}.html"
# Shown first when the data are sensitive; the rest keep the table's order.
SENSITIVE_FIRST = ("restricted", "closed")

LIMITATIONS = (
    "It offers a short fixed list of licences and reads no licence texts. Drawing them from the "
    "SPDX licence list is planned (#877).",
    "It does not check what your funder, journal, institution or repository requires or offers.",
    "It does not judge whether the data are sensitive or who holds rights in them.",
    "Without an interpreter model (DD_RIGHTS_INTERPRETER=template), it understands the reuse you "
    "want only as one of any, attribution, share-alike or non-commercial.",
    "A model's reading of the reuse you want is a reading of your words, not advice: check it. "
    "It has no evaluation set yet, so how often it misreads is not measured.",
    "It is not legal advice.",
)
CHOOSE_QUESTION = (
    "Choose the licence and access level yourself, and check that your repository offers them."
)
REUSE_QUESTION = (
    "Say what reuse of the data you want to allow: any, with attribution, share-alike or "
    "non-commercial."
)
SENSITIVE_QUESTION = (
    "The data are sensitive. Decide the access level with your institution's ethics and data "
    "protection staff before deposit."
)
UNKNOWN_SENSITIVE_QUESTION = (
    "Say whether the data hold personal or otherwise sensitive information."
)
THIRD_PARTY_QUESTION = (
    "The data include content from third parties. Confirm that their terms allow you to share it "
    "under the licence you choose, with your institution's copyright or research support staff."
)
MANDATED_NOTE = "Mandated, as you said. Confirm the mandate's exact wording before deposit."
READ_AS_QUESTION = (
    "A model read the reuse you want to allow ('{said}') as: {read}. Check that reading; the "
    "licences listed follow from it."
)
MANDATED_REUSE_QUESTION = (
    "The mandated licence may not match the reuse you said you want to allow. Ask whoever "
    "mandates it whether another licence is acceptable."
)


def load_table(path: Path = LICENCES) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        table: dict[str, Any] = yaml.safe_load(fh)
    return table


class RightsAdviser:
    spec = AgentSpec(
        agent_id="advisor.rights",
        version="0.2.0a1",
        title="Rights and Licensing Adviser",
        description=(
            "Alpha. Lists data licences that fit the reuse a researcher wants to allow, and the "
            "access levels with when each applies, for the researcher to choose from. With a "
            "model, it reads a reuse wish in the researcher's own words and tailors its "
            "questions, choosing only from its own table of licences. Never chooses a licence "
            "or an access level."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(RightsContext),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(RightsOptions),
        derivations={
            "licences.spdx_id": Derived(Derivation.MODEL, recorded_in="derivation"),
            "licences.name": Derived(Derivation.TEMPLATE),
            "licences.url": Derived(Derivation.TEMPLATE),
            "licences.note": Derived(Derivation.TEMPLATE),
            "access_levels.level": Derived(Derivation.TEMPLATE),
            "access_levels.when": Derived(Derivation.TEMPLATE),
            "questions.text": Derived(Derivation.MODEL, recorded_in="derivation"),
            "limitations": Derived(Derivation.TEMPLATE),
            "dropped": Derived(Derivation.TEMPLATE),
        },
        serves=("deposit.licence", "deposit.access"),
    )

    def __init__(
        self, table: dict[str, Any] | None = None, interpreter: Interpreter | None = None
    ) -> None:
        self.table = table if table is not None else load_table()
        self.interpreter: Interpreter = (
            TemplateInterpreter() if interpreter is None else interpreter
        )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, RightsContext)  # the conductor checked spec.accepts
        if (
            context.reuse_wanted is None
            and context.sensitive is None
            and context.mandated_licence is None
            and context.third_party_content is None
        ):
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                (
                    "Say what reuse you want to allow, whether the data are sensitive, any "
                    "licence you are required to use, or whether they include third-party "
                    "content."
                ),
            )

        template, model = Derivation.TEMPLATE, Derivation.MODEL
        questions: list[RightsQuestion] = [
            RightsQuestion(text=CHOOSE_QUESTION, derivation=template)
        ]
        said = (context.reuse_wanted or "").strip()
        reuse = key(said)
        known = {fit for entry in self.table["licences"] for fit in entry["fits"]}
        by_rule = reuse in known

        # What follows by rule alone, before any model is called: the access levels and the
        # questions the rules always ask.
        levels = list(self.table["access_levels"])
        later: list[str] = []
        if context.sensitive:
            levels = [*SENSITIVE_FIRST, *(lv for lv in levels if lv not in SENSITIVE_FIRST)]
            later.append(SENSITIVE_QUESTION)
        elif context.sensitive is None:
            later.append(UNKNOWN_SENSITIVE_QUESTION)
        if context.third_party_content:
            later.append(THIRD_PARTY_QUESTION)

        reading = self.interpreter.read(
            Asked(
                table=self.table,
                reuse_wanted=said if said and not by_rule else None,
                mandated_licence=context.mandated_licence,
                third_party_content=context.third_party_content,
                fixed_questions=(CHOOSE_QUESTION, REUSE_QUESTION, *later),
            ),
            ctx,
        )

        if context.mandated_licence:
            licences = [self._mandated(context.mandated_licence)]
            entry = self._entry(context.mandated_licence)
            if entry is not None and by_rule and reuse not in entry["fits"]:
                questions.append(RightsQuestion(text=MANDATED_REUSE_QUESTION, derivation=template))
            elif (
                entry is not None and reading.reuse and not set(reading.reuse) & set(entry["fits"])
            ):
                questions.append(RightsQuestion(text=MANDATED_REUSE_QUESTION, derivation=model))
        elif by_rule:
            licences = [self._option(e) for e in self.table["licences"] if reuse in e["fits"]]
        elif reading.licences:
            rows = {e["spdx_id"]: e for e in self.table["licences"]}
            licences = [
                self._option(rows[i]).model_copy(update={"derivation": model})
                for i in reading.licences
            ]
            questions.append(
                RightsQuestion(
                    text=READ_AS_QUESTION.format(said=said, read=", ".join(reading.reuse)),
                    derivation=model,
                )
            )
        else:  # reuse unknown or unread: offer them all
            licences = [self._option(e) for e in self.table["licences"]]
            questions.append(RightsQuestion(text=REUSE_QUESTION, derivation=template))

        questions += [RightsQuestion(text=q, derivation=template) for q in later]
        questions += [RightsQuestion(text=q, derivation=model) for q in reading.questions]
        access = [AccessOption(level=lv, when=self.table["access_levels"][lv]) for lv in levels]

        calls = reading.calls
        ref = input_ref(ctx)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"{_count(len(licences), 'licence option')} and {len(access)} access levels "
                    "to choose from. The researcher chooses; the adviser does not. "
                    + _how_read(reading)
                ),
            ),
            payload=RightsOptions(
                licences=licences,
                access_levels=access,
                questions=questions,
                limitations=list(LIMITATIONS),
                dropped=list(reading.dropped),
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
            model_id=reading.model_id if reading.called else None,
            input_tokens=reading.usage.input_tokens,
            output_tokens=reading.usage.output_tokens,
            model_calls=tuple(calls.calls) if calls is not None else (),
            prompts=dict(calls.prompts) if calls is not None else {},
        )

    def _entry(self, spdx_id: str) -> dict[str, Any] | None:
        wanted = spdx_id.strip().lower()
        return next((e for e in self.table["licences"] if e["spdx_id"].lower() == wanted), None)

    def _mandated(self, spdx_id: str) -> LicenceOption:
        entry = self._entry(spdx_id)
        if entry is None:  # not in the table: name it as given, with SPDX's page for it
            spdx_id = spdx_id.strip()
            return LicenceOption(
                spdx_id=spdx_id,
                name=spdx_id,
                url=SPDX_URL.format(spdx_id),
                note=MANDATED_NOTE,
                derivation=Derivation.TEMPLATE,
            )
        return self._option(entry).model_copy(update={"note": MANDATED_NOTE})

    @staticmethod
    def _option(entry: dict[str, Any]) -> LicenceOption:
        note = entry.get("note")
        return LicenceOption(
            spdx_id=entry["spdx_id"],
            name=entry["name"],
            url=entry["url"],
            note=" ".join(note.split()) if note else None,
            derivation=Derivation.TEMPLATE,
        )


def _how_read(reading: Reading) -> str:
    """What the statement says about the interpreter: whether a model read what the rules could
    not, and what it changed or why it was not used."""
    if reading.model_id is None:
        return (
            "They follow by rule: no interpreter model is configured, so the reuse wanted is "
            "understood only as one of the table's values."
        )
    if not reading.called:
        return (
            f"They follow by rule; there was nothing for the interpreter model "
            f"({reading.model_id}) to read."
        )
    if reading.unused:
        return f"They follow by rule, because {reading.unused} ({reading.model_id})."
    said = f"A model ({reading.model_id}) read what the rules could not"
    if reading.reuse:
        said += f", reading the reuse wanted as {', '.join(reading.reuse)}"
    said += f", and added {_count(len(reading.questions), 'question')}"
    if reading.dropped:
        said += (
            f"; {_count(len(reading.dropped), 'part')} of its reply "
            f"{'was' if len(reading.dropped) == 1 else 'were'} not used ("
            + "; ".join(reading.dropped)
            + ")"
        )
    return said + ". Check its reading."


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def build() -> RightsAdviser:
    """The template adviser. `factory.build` reads the agent's settings."""
    return RightsAdviser()
