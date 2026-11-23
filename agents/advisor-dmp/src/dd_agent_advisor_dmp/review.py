"""A review of the data management plan the researcher attached (`setup.dmp-review`): how well it
answers the core requirements of a plan, and whether it reflects what people in the project decided.

There is no rule behind it. A plan's headings say little about whether it answers a requirement,
and a decision's wording may differ from the plan's, so the review is a model's reading
(`review_model.py`, `review_prompt.md`), with every reading checked by code before it is used. Here
are what that reading is given and how it is counted:

- The plan is the document a person marked as the project's plan (#1447), or, while none is
  marked, the latest document attached (`plan_of`).
- The decisions are the funder, a required repository, a licence and a standard people in the
  project chose, and any sensitive data they identified, so that the model can say where the plan
  does not reflect one (`decisions_of`).

Every finding is advice for a person: the review never changes the plan.
"""

from __future__ import annotations

from collections.abc import Sequence

from dd_agent_advisor_dmp.classes import SectionFinding
from dd_dmp_template import SECTIONS
from dd_sdk.contract.facts import FactKind, ProjectDocument, ProjectFact

# For each kind of decision a plan should reflect, what it is called and the slot holding its value.
NAMED_DECISIONS: dict[FactKind, tuple[str, str]] = {
    FactKind.FUNDER: ("funder", "fact_funder_name"),
    FactKind.REQUIRED_REPOSITORY: ("required repository", "fact_repository_name"),
    FactKind.LICENCE: ("licence", "licence_id"),
    FactKind.STANDARD: ("standard", "standard_name"),
}


def plan_of(documents: Sequence[ProjectDocument]) -> ProjectDocument | None:
    """The plan reviewed: the document marked as the project's plan, or, while none is, the
    latest document attached; None if none is attached."""
    candidates = [d for d in documents if d.documentation_is_plan] or list(documents)
    return candidates[-1] if candidates else None


def decisions_of(decisions: Sequence[ProjectFact]) -> list[dict[str, str]]:
    """The decisions a plan should reflect, each as its kind and what was decided."""
    found: list[dict[str, str]] = []
    for fact in decisions:
        if fact.fact_kind == FactKind.SENSITIVITY:
            subject = fact.sensitive_subject or fact.fact_subject
            found.append({"decision": "sensitive data identified", "decided": subject})
        elif fact.fact_kind in NAMED_DECISIONS:
            what, slot = NAMED_DECISIONS[fact.fact_kind]
            if value := getattr(fact, slot):
                found.append({"decision": what, "decided": value})
    return found


def counted(findings: Sequence[SectionFinding]) -> str:
    """How many requirements the review found covered, vague and missing."""
    by = {k: sum(f.finding == k for f in findings) for k in ("covered", "vague", "missing")}
    return (
        f"Of the {len(SECTIONS)} core requirements, a model read the plan as answering "
        f"{by['covered']} specifically enough, {by['vague']} only in part or in general terms and "
        f"{by['missing']} not at all"
    )
