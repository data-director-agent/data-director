"""A review of the data management plan the researcher attached (`setup.dmp-review`): which of the
core requirements it covers, and where it disagrees with what people in the project decided.

Rules first, and they stand on their own, so a review needs no model:

- The plan is the latest document attached. `dd_dmp_template.coverage` reads its headings: a core
  requirement a heading names, with text under it, is `covered`; one whose heading has nothing
  under it is `vague`; one no heading names is `missing`.
- A decision people made that the plan does not name is a `DecisionConflict`: a funder, a required
  repository, a licence or a standard it never mentions (as text, once case, spaces, quotation
  marks and dashes are set aside), or sensitive data where the plan has no section on legal and
  ethical requirements.

Then, with a model configured (`DD_DMP_MATCHER`, `review_model.py`), the model reads the plan
against each requirement's questions. It may raise a finding, from `covered` to `vague`, with its
reason and a quote that must be found in the plan; it may point to where a requirement the rules
found `missing` is answered under another heading, which stays `missing` with the model's reason
and quote, for a person to judge. It never lowers a rule's finding, and a reply it cannot use
leaves the rules' review, and the statement says why.

Every finding is advice for a person: the review never changes the plan.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from dd_agent_advisor_dmp.classes import DecisionConflict, SectionFinding
from dd_agent_advisor_dmp.read_plan import normalise
from dd_dmp_template import SECTIONS, Coverage, coverage
from dd_sdk.contract.facts import FactKind, ProjectDocument, ProjectFact
from dd_sdk.contract.models import Derivation

# The most of a passage quoted as the words a covered finding rests on, in characters.
MAX_QUOTED = 300
LEGAL = "legal-ethical"

COVERED = "The plan covers this under '{heading}'. Check that it answers: {questions}"
EMPTY = (
    "The plan has a heading for this, '{heading}', but nothing under it. It should answer: "
    "{questions}"
)
MISSING = "No heading of the plan names this requirement. A plan should answer: {questions}"
NOT_NAMED = (
    "People in the project decided on {what} '{decided}', which the plan does not name. A person "
    "should review whether the plan needs updating."
)
NO_LEGAL_SECTION = (
    "Sensitive data were identified ({decided}), but the plan has no section on legal and "
    "ethical requirements. A person should review how the plan handles them."
)
# What each kind of decision is called in a message, and the value the plan should name.
NAMED_DECISIONS: dict[FactKind, tuple[str, str]] = {
    FactKind.FUNDER: ("the funder", "fact_funder_name"),
    FactKind.REQUIRED_REPOSITORY: ("the repository", "fact_repository_name"),
    FactKind.LICENCE: ("the licence", "licence_id"),
    FactKind.STANDARD: ("the standard", "standard_name"),
}


@dataclass(frozen=True)
class Reviewed:
    """What the rules found in a plan."""

    findings: list[SectionFinding] = field(default_factory=list)
    conflicts: list[DecisionConflict] = field(default_factory=list)


def plan_of(documents: Sequence[ProjectDocument]) -> ProjectDocument | None:
    """The plan reviewed: the latest document attached, or None if none is."""
    return documents[-1] if documents else None


def review(plan: ProjectDocument, decisions: Sequence[ProjectFact]) -> Reviewed:
    """The rules' review of `plan` against the core requirements and the decisions made."""
    covered = coverage(plan.documentation_text)
    findings = [finding(c) for c in covered]
    return Reviewed(findings, conflicts(plan.documentation_text, decisions, covered))


def finding(found: Coverage) -> SectionFinding:
    """One requirement's finding, by rule."""
    questions = " ".join(found.section.questions)
    section = found.section.heading
    if not found.covered:
        return SectionFinding(
            section=section,
            finding="missing",
            message=MISSING.format(questions=questions),
            finding_derivation=Derivation.LEXICAL,
        )
    under = next((p for p in found.passages if p.text.strip()), None)
    heading = (under or found.passages[0]).heading
    if under is None:
        return SectionFinding(
            section=section,
            finding="vague",
            plan_heading=heading,
            message=EMPTY.format(heading=heading, questions=questions),
            finding_derivation=Derivation.LEXICAL,
        )
    return SectionFinding(
        section=section,
        finding="covered",
        plan_heading=heading,
        quote=quoted(under.text),
        message=COVERED.format(heading=heading, questions=questions),
        finding_derivation=Derivation.LEXICAL,
    )


def quoted(text: str) -> str:
    """The start of a passage, at most `MAX_QUOTED` characters, cut at a word."""
    flat = " ".join(text.split())
    if len(flat) <= MAX_QUOTED:
        return flat
    return flat[:MAX_QUOTED].rsplit(" ", 1)[0] + " …"


def conflicts(
    text: str, decisions: Sequence[ProjectFact], covered: Sequence[Coverage]
) -> list[DecisionConflict]:
    """The decisions the plan does not reflect, in the order they were decided."""
    plan = normalise(text)
    found: list[DecisionConflict] = []
    has_legal = any(c.covered for c in covered if c.section.id == LEGAL)
    for fact in decisions:
        if fact.fact_kind == FactKind.SENSITIVITY and not has_legal:
            subject = fact.sensitive_subject or fact.fact_subject
            found.append(
                DecisionConflict(
                    fact_kind=fact.fact_kind,
                    decided=subject,
                    message=NO_LEGAL_SECTION.format(decided=subject),
                )
            )
            continue
        if fact.fact_kind not in NAMED_DECISIONS:
            continue
        what, slot = NAMED_DECISIONS[fact.fact_kind]
        value = getattr(fact, slot)
        if value and normalise(value) not in plan:
            found.append(
                DecisionConflict(
                    fact_kind=fact.fact_kind,
                    decided=value,
                    message=NOT_NAMED.format(what=what, decided=value),
                )
            )
    return found


def counted(findings: Sequence[SectionFinding]) -> str:
    """How many requirements the review found covered, vague and missing."""
    by = {k: sum(f.finding == k for f in findings) for k in ("covered", "vague", "missing")}
    return (
        f"Of the {len(SECTIONS)} core requirements, the plan covers {by['covered']}, treats "
        f"{by['vague']} too vaguely to answer them and has no section for {by['missing']}"
    )
