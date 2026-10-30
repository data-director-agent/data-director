"""advisor.rights: the Rights and Licensing Adviser persona (ADR-0033). A mock.

Serves `deposit.licence` and `deposit.access`. It lists data licences that fit the reuse the
researcher wants to allow, and the access levels with when each applies, and asks the questions
a person must answer first. The researcher chooses: it never picks a licence or an access level.

The mock reads its options from `licences.yaml`. It consults no source and calls no model, so its
grounding mode is `none` and it cites only its input. The real adviser, drawing on the SPDX
licence list, funder mandates through advisor.policy and the repository's licence options, is
TODO(#359).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_rights.classes import (
    AccessOption,
    LicenceOption,
    RightsContext,
    RightsOptions,
)
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

LICENCES = Path(__file__).with_name("licences.yaml")
SPDX_URL = "https://spdx.org/licenses/{}.html"
# Shown first when the data are sensitive; the rest keep the table's order.
SENSITIVE_FIRST = ("restricted", "closed")

LIMITATIONS = (
    "This is a mock: it offers a short fixed list of licences and reads no licence texts.",
    "It does not check what your funder, journal, institution or repository requires or offers.",
    "It does not judge whether the data are sensitive or who holds rights in them.",
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
        version="0.1.0a1",
        title="Rights and Licensing Adviser",
        description=(
            "Mock. Lists data licences that fit the reuse a researcher wants to allow, and the "
            "access levels with when each applies, for the researcher to choose from. Never "
            "chooses a licence or an access level."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(RightsContext),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(RightsOptions),
        derivations={
            "licences.spdx_id": Derived(Derivation.TEMPLATE),
            "licences.name": Derived(Derivation.TEMPLATE),
            "licences.url": Derived(Derivation.TEMPLATE),
            "licences.note": Derived(Derivation.TEMPLATE),
            "access_levels.level": Derived(Derivation.TEMPLATE),
            "access_levels.when": Derived(Derivation.TEMPLATE),
            "questions": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("deposit.licence", "deposit.access"),
    )

    def __init__(self, table: dict[str, Any] | None = None) -> None:
        self.table = table if table is not None else load_table()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, RightsContext)  # the conductor checked spec.accepts
        if (
            context.reuse_wanted is None
            and context.sensitive is None
            and context.mandated_licence is None
            and context.third_party_content is None
        ):
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement=(
                        "Say what reuse you want to allow, whether the data are sensitive, any "
                        "licence you are required to use, or whether they include third-party "
                        "content."
                    ),
                )
            )

        questions = [CHOOSE_QUESTION]
        reuse = (context.reuse_wanted or "").strip().lower()
        known = {fit for entry in self.table["licences"] for fit in entry["fits"]}
        if context.mandated_licence:
            licences = [self._mandated(context.mandated_licence)]
            entry = self._entry(context.mandated_licence)
            if reuse in known and entry is not None and reuse not in entry["fits"]:
                questions.append(MANDATED_REUSE_QUESTION)
        else:
            entries = [e for e in self.table["licences"] if reuse in e["fits"]]
            if not entries:  # reuse unknown or unrecognised: offer them all
                entries = self.table["licences"]
                questions.append(REUSE_QUESTION)
            licences = [self._option(e) for e in entries]

        levels = list(self.table["access_levels"])
        if context.sensitive:
            levels = [*SENSITIVE_FIRST, *(lv for lv in levels if lv not in SENSITIVE_FIRST)]
            questions.append(SENSITIVE_QUESTION)
        elif context.sensitive is None:
            questions.append(UNKNOWN_SENSITIVE_QUESTION)
        if context.third_party_content:
            questions.append(THIRD_PARTY_QUESTION)
        access = [AccessOption(level=lv, when=self.table["access_levels"][lv]) for lv in levels]

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: {len(licences)} licence option{'s' if len(licences) != 1 else ''} "
                    f"and {len(access)} access levels to choose from. The researcher chooses; "
                    "the adviser does not."
                ),
            ),
            payload=RightsOptions(
                licences=licences,
                access_levels=access,
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

    def _entry(self, spdx_id: str) -> dict[str, Any] | None:
        wanted = spdx_id.strip().lower()
        return next((e for e in self.table["licences"] if e["spdx_id"].lower() == wanted), None)

    def _mandated(self, spdx_id: str) -> LicenceOption:
        entry = self._entry(spdx_id)
        if entry is None:  # not in the table: name it as given, with SPDX's page for it
            spdx_id = spdx_id.strip()
            return LicenceOption(
                spdx_id=spdx_id, name=spdx_id, url=SPDX_URL.format(spdx_id), note=MANDATED_NOTE
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
        )


def build() -> RightsAdviser:
    return RightsAdviser()


def main() -> int:
    """The `dd-advisor-rights` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
