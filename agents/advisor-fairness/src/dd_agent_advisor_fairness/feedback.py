"""Constructive feedback from the rule table's verdicts: what is met first, a tally for each of F,
A, I and R, and the next steps most worth taking (#430). Every value here is decided by rule; a
tally counts presence checks and is not a FAIR score (R4)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dd_agent_advisor_fairness.classes import FairPrinciple, PrincipleTally, PublishedRecord
from dd_agent_advisor_fairness.rules import Rule, meets

# How many unmet checks the report names as next steps.
NEXT_STEPS = 2


@dataclass(frozen=True)
class Verdict:
    """One rule's verdict on a record. `after_deposit` is set when a draft does not meet a check
    the repository fills at deposit: it is neither counted nor recommended."""

    rule: Rule
    met: bool
    after_deposit: bool = False
    newly_met: bool | None = None

    @property
    def to_act_on(self) -> bool:
        return not self.met and not self.after_deposit


def judge(
    rules: Sequence[Rule],
    record: PublishedRecord,
    *,
    draft: bool,
    approved: PublishedRecord | None = None,
) -> list[Verdict]:
    """Each rule's verdict on `record`, best first (`ordered`). For a `draft`, a check the
    repository fills at deposit and not met is `after_deposit`. With an `approved` record, each
    verdict says whether the check is newly met since."""
    verdicts = []
    for rule in rules:
        met = meets(rule, record)
        verdicts.append(
            Verdict(
                rule,
                met,
                after_deposit=draft and rule.after_deposit and not met,
                newly_met=(met and not meets(rule, approved)) if approved is not None else None,
            )
        )
    return ordered(verdicts)


def ordered(verdicts: Sequence[Verdict]) -> list[Verdict]:
    """What is met first, in table order; then what to act on, by priority; then what is left
    until deposit."""
    met = [v for v in verdicts if v.met]
    to_act_on = sorted((v for v in verdicts if v.to_act_on), key=lambda v: v.rule.priority)
    later = [v for v in verdicts if v.after_deposit]
    return [*met, *to_act_on, *later]


def tallies(verdicts: Sequence[Verdict]) -> list[PrincipleTally]:
    """For each of F, A, I and R, how many of its assessed checks are met. A check left until
    deposit is not assessed."""
    counts: dict[FairPrinciple, list[int]] = {p: [0, 0] for p in FairPrinciple}
    for verdict in verdicts:
        if verdict.after_deposit:
            continue
        count = counts[FairPrinciple(verdict.rule.principle[0])]
        count[0] += verdict.met
        count[1] += 1
    return [
        PrincipleTally(principle_group=p, tally_met=met, tally_assessed=assessed)
        for p, (met, assessed) in counts.items()
    ]


def next_steps(verdicts: Sequence[Verdict]) -> list[str]:
    """The checks to act on, highest priority first, at most `NEXT_STEPS`."""
    to_act_on = sorted((v for v in verdicts if v.to_act_on), key=lambda v: v.rule.priority)
    return [v.rule.check for v in to_act_on[:NEXT_STEPS]]


def summary(
    whose: str,
    verb: str,
    verdicts: Sequence[Verdict],
    counted: Sequence[PrincipleTally],
    steps: Sequence[str],
) -> str:
    """The statement's first sentences, `whose` metadata as their subject and `verb` its verb:
    what is met first, by principle, then the next step."""
    met = sum(t.tally_met for t in counted)
    assessed = sum(t.tally_assessed for t in counted)
    by_principle = ", ".join(
        f"{t.principle_group.value} {t.tally_met}/{t.tally_assessed}"
        for t in counted
        if t.tally_assessed
    )
    already = "already " if met else ""
    said = f"{whose} {already}{verb} {met} of {assessed} checks ({by_principle})."
    newly = sum(bool(v.newly_met) for v in verdicts)
    if newly:
        said += f" {newly} {'is' if newly == 1 else 'are'} newly met since the version approved."
    if steps:
        first: Mapping[str, Rule] = {v.rule.check: v.rule for v in verdicts}
        said += f" Next: {first[steps[0]].recommendation}"
    elif assessed:
        said += " Every check assessed is met."
    return said
