"""Explainers: turn already-assessed policies into rationale (Blueprint P8, C14).

An explainer receives policy records that were retrieved, matched and assessed before it is
called, and returns one rationale per policy. `TemplateExplainer` writes it from a fixed template,
needs no credentials, and changes nothing else; it is used with `DD_POLICY_ADVISOR=template`, and
whenever the model advisor cannot answer.

The model advisor (`advise.ModelAdvisor`, the default) has the same interface. It may also add
obligations it read in a record, each with a quote the agent finds in that record, and policy
records it found with its search tools (`Explanation.obligations`, `Explanation.found`). It
cannot remove a policy the first search matched, nor change an obligation read by rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from dd_agent_advisor_policy.classes import Actor, Obligation, PolicyContext, Strength
from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_sdk import explain
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.explain import Rationale as Rationale
from dd_sdk.model import Usage as Usage

if TYPE_CHECKING:
    from dd_agent_advisor_policy.tools import Lookups


@dataclass(frozen=True)
class Item:
    """What an explainer is told about one matched policy."""

    record: SourceRecord
    actor: Actor
    obligations: tuple[Obligation, ...]
    notes: tuple[str, ...]
    # How the record was matched to the actor: by the first search's rule, or by a model.
    matched_by: Derivation = Derivation.REGISTRY


@dataclass(frozen=True)
class Explanation(explain.Explanation):
    """One rationale per item, and the tokens spent (`dd_sdk.explain.Explanation`), and what the
    model advisor may say besides."""

    # Each item's obligations after a model's verified additions; None leaves them as they were.
    obligations: list[tuple[Obligation, ...]] | None = None
    # Each item's notes after the model advisor's; None leaves them as they were.
    notes: list[tuple[str, ...]] | None = None
    # Policies a model found with its tools, each with its rationale.
    found: list[tuple[Item, Rationale]] = field(default_factory=list)
    # What the run should say about the model's part, e.g. claims dropped and why.
    remarks: list[str] = field(default_factory=list)


class Explainer(Protocol):
    model_id: str | None

    def explain(
        self,
        context: PolicyContext,
        items: list[Item],
        ctx: RunContext,
        lookups: Lookups | None = None,
    ) -> Explanation: ...


def _kinds(item: Item, strength: Strength) -> str:
    return ", ".join(
        o.kind.value.replace("_", " ") for o in item.obligations if o.strength == strength
    )


def template_rationale(item: Item) -> str:
    r = item.record
    kind = (getattr(r, "kind", None) or "policy").replace("_", " ")
    parts = [f"{r.label} is the {kind} policy {r.registry} holds for {item.actor.name}."]
    for strength, verb in ((Strength.REQUIRED, "requires"), (Strength.RECOMMENDED, "recommends")):
        kinds = _kinds(item, strength)
        if kinds:
            parts.append(f"The record says it {verb}: {kinds}.")
    unstated = _kinds(item, Strength.UNSTATED)
    if unstated:
        parts.append(f"It does not state: {unstated}.")
    if r.registry == "FAIRsharing":
        parts.append(
            "These are read from FAIRsharing's curated record, not from the policy's own text; "
            "check the policy before relying on them."
        )
    else:
        parts.append(
            f"{r.registry}'s record states open access policy, mostly about publications; no "
            "obligation was read from it by rule. Read the record, and the policy itself, before "
            "relying on it."
        )
    return " ".join(parts)


class TemplateExplainer(explain.TemplateExplainer[PolicyContext, Item, Explanation]):
    def rationale(self, item: Item) -> str:
        return template_rationale(item)

    def result(self, rationales: list[Rationale], usage: Usage) -> Explanation:
        return Explanation(rationales, usage)
