"""Explainers: turn already-decided candidates into rationale (Blueprint P8, C14).

An explainer receives repositories that were retrieved, assessed and ranked before it is called,
and returns one rationale per candidate. It cannot add, remove or reorder candidates, nor change
a judgement. If a model's rationale names a re3data or FAIRsharing identifier it was not given,
the template rationale is used instead and the substitution is noted in the text.

`ModelExplainer` is the default (`DD_REPOSITORY_EXPLAINER` unset or `model`); `TemplateExplainer`
is selected with `DD_REPOSITORY_EXPLAINER=template` and needs no credentials. `ModelExplainer`
calls whichever model the agent's settings name, through
the SDK's model seam (`dd_sdk.model`, `dd_sdk.model_provider`).
It is sent registry text and the needs, never research data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dd_agent_advisor_repository.assess import Assessment, fee_required
from dd_agent_advisor_repository.classes import Answer, CandidateBasis, RepositoryNeeds
from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_sdk import explain
from dd_sdk.agent import RunContext
from dd_sdk.explain import Explanation as Explanation
from dd_sdk.explain import Rationale as Rationale
from dd_sdk.model import Usage as Usage


@dataclass(frozen=True)
class Item:
    """What an explainer is told about one candidate."""

    record: Re3dataRecord
    database: DatabaseRecord | None
    basis: CandidateBasis
    assessment: Assessment
    reasons: tuple[str, ...]


class Explainer(Protocol):
    model_id: str | None

    def explain(
        self, needs: RepositoryNeeds, items: list[Item], ctx: RunContext
    ) -> Explanation: ...


IDENTIFIER = re.compile(r"\b(r3d\d+|FAIRsharing\.[0-9A-Za-z-]+)", re.IGNORECASE)


def template_rationale(item: Item) -> str:
    r = item.record
    if item.basis == CandidateBasis.MANDATED:
        lead = f"{r.name} ({r.re3data_id}) was named as mandated, so it is described, not ranked."
    elif item.basis == CandidateBasis.ASKED_ABOUT:
        why = f" {' '.join(item.reasons)}" if item.reasons else ""
        lead = (
            f"{r.name} ({r.re3data_id}) is described because the researcher asked about it; "
            f"no policy given requires it.{why}"
        )
    elif item.basis == CandidateBasis.IN_PLAN:
        why = f" {' '.join(item.reasons)}" if item.reasons else ""
        lead = (
            f"{r.name} ({r.re3data_id}) is described because the project's data management "
            f"plan names it; no policy given requires it.{why}"
        )
    elif item.basis == CandidateBasis.CHOSEN:
        lead = (
            f"{r.name} ({r.re3data_id}) is the repository the researcher chose, so it is described."
        )
    else:
        why = f" {' '.join(item.reasons)}" if item.reasons else ""
        lead = f"{r.name} ({r.re3data_id}) is shortlisted.{why}"
    kind = f" re3data lists it as {', '.join(r.types)}." if r.types else ""
    subjects = f" Subjects: {'; '.join(r.subject_names()[:3])}." if r.subjects else ""
    gaps = (
        f" Not met or not stated: {' '.join(item.assessment.misses)}"
        if item.assessment.misses
        else ""
    )
    return (
        f"{lead}{kind}{subjects}{gaps} {FEE[fee_required(r)]} The researcher chooses; "
        "the repositories were found by registry search and ranking, not by a model."
    )


# What the rationale says of a deposit fee. re3data can say a fee is required but never that none
# is, so a fee it does not list is one the repository has not stated, not one it does not charge.
FEE = {
    Answer.YES: "A deposit fee is listed; re3data gives no amount, so ask the repository.",
    Answer.NO: "No deposit fee is listed.",
    Answer.UNSTATED: "Deposit fee: not stated by the repository, check with them.",
}


class TemplateExplainer(explain.TemplateExplainer[RepositoryNeeds, Item]):
    def rationale(self, item: Item) -> str:
        return template_rationale(item)


DEFAULT_MODEL = "claude-sonnet-5-5"

# What the model is told it may and may not do; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()


class ModelExplainer(explain.ModelExplainer[RepositoryNeeds, Item]):
    """Explains with the model the agent's settings name (`dd_sdk.model_provider`), in one call
    (`dd_sdk.explain.ModelExplainer`)."""

    system_prompt = SYSTEM_PROMPT
    pattern = IDENTIFIER

    def prompt(self, needs: RepositoryNeeds, items: list[Item]) -> str:
        lines = [
            "Needs:",
            f"  themes: {', '.join(needs.themes) or '(none)'}",
            f"  kinds of data: {', '.join(needs.data_kinds) or '(none)'}",
            f"  access: {needs.access or '(not decided)'}",
            f"  affiliation: {needs.affiliation.name if needs.affiliation else '(none)'}",
            "",
            "Repositories:",
        ]
        for n, item in enumerate(items, start=1):
            r, a = item.record, item.assessment
            desc = (r.description or "").strip().replace("\n", " ")
            lines.append(
                f"{n}. {r.name} [{r.re3data_id}] — basis: {item.basis.value}; "
                f"types: {', '.join(r.types)}; subjects: {'; '.join(r.subject_names()[:6])}; "
                f"meets: {' '.join(a.meets) or '(none)'}; "
                f"misses: {' '.join(a.misses) or '(none)'}; "
                f"notes: {' '.join(a.notes) or '(none)'}; "
                f"deposit fee: {FEE[fee_required(r)]}; "
                f"registry description: {desc[:600]}"
            )
        return "\n".join(lines)

    def template(self, item: Item) -> str:
        return template_rationale(item)

    def allowed(self, items: list[Item]) -> set[str]:
        ids = {item.record.re3data_id for item in items}
        return ids | {i.record.fairsharing_id for i in items if i.record.fairsharing_id}
