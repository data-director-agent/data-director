"""The agent's result from what it found and advised: the statement, the `PolicyChecks` payload
and the evidence each cited record rests on. Every sentence is a template over what the code
found; a model's words reach the statement only as its remarks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dd_agent_advisor_policy import assess
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    MatchedPolicy,
    PolicyChecks,
    PolicyConflict,
    PolicyRegistry,
    RepositoryRef,
    SearchedSummary,
    Strength,
)
from dd_agent_advisor_policy.explain import Explanation, Item, Rationale
from dd_agent_advisor_policy.grounding import org_evidence, org_ref, record_evidence, record_ref
from dd_agent_advisor_policy.reading import TextReadings
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_agent_advisor_policy.search import FirstSearch
from dd_mcp_pid.ror_records import Organisation
from dd_sdk.agent import AgentResult, abstain
from dd_sdk.contract.models import Derivation, EvidenceItem, Outcome, OutcomeStatus, ReasonCode

Advised = list[tuple[Item, Rationale]]

# What every payload says it does not do. Each line is true of the code: the sources it reads, what
# a record is, and what a model's reading of policy text is worth.
LIMITATIONS = (
    "It reads FAIRsharing and Jisc Open Policy Finder for policies, Crossref for a journal's "
    "publisher and ROR for a funder's identity. Where a model reads policy text, it also reads the "
    "pages those records or the researcher name. No other source is searched, so a policy that "
    "none of them holds is not found.",
    "A registry record is a curated summary, not the policy itself. An obligation taken from a "
    "record is read by fixed rules from its curated fields, and a person checks it against the "
    "policy.",
    "The FAIRsharing and ROR data is a dated snapshot by default, so a change made since its date "
    "is not shown.",
    "Where a model reads a policy's own text, each obligation kept quotes that text word for word, "
    "and the code has found the quote in it. The kind, strength and value are the model's reading "
    "of the quote, and a person confirms each against the policy.",
    "Open Policy Finder is not searched without an API key. A registry that cannot be asked is "
    "named in the statement.",
    "It does not decide which of differing policies applies, nor whether an actor meets a policy's "
    "requirements.",
    "It is an alpha with no evaluation set yet: how many policies it misses is not measured.",
)


def _candidate(org: Organisation) -> str:
    where = f", {', '.join(org.country_codes)}" if org.country_codes else ""
    return f"{org.label} ({org.id}{where})"


def _ambiguity(actor: Actor, candidates: tuple[Organisation, ...]) -> str:
    return (
        f"{actor.name!r} could be any of {len(candidates)} organisations in ROR: "
        + "; ".join(_candidate(o) for o in candidates)
        + ". Say which, by giving its ROR identifier, and its policy will be looked up."
    )


def _journal_ambiguity(actor: Actor, candidates: Sequence[SourceRecord]) -> str:
    return (
        f"{actor.name!r} could be any of {len(candidates)} journals: "
        + "; ".join(c.label for c in candidates)
        + ". Say which, by giving its ISSN, and its policy will be looked up."
    )


def _registry(record: SourceRecord) -> PolicyRegistry:
    return (
        PolicyRegistry.FAIRSHARING
        if isinstance(record, PolicyRecord)
        else PolicyRegistry.OPEN_POLICY_FINDER
    )


def opf_note(found: FirstSearch) -> str:
    """Why Open Policy Finder was not searched, and which registries could not be asked."""
    note = ""
    if found.sources.opf is None and any(
        a.role in (ActorRole.FUNDER, ActorRole.JOURNAL) for a in found.actors
    ):
        note = (
            " Open Policy Finder was not searched: no OPEN_POLICY_FINDER_API_KEY is set, so "
            "funders' and journals' open access policies were not checked."
        )
    if found.opf.problems:
        note += (
            " Not every registry could be asked: "
            + "; ".join(dict.fromkeys(found.opf.problems))
            + "."
        )
    return note


def model_use(
    explanation: Explanation,
    texts: TextReadings,
    explainer_model: str | None,
    extractor_model: str | None,
) -> dict[str, Any]:
    """The models called in this run, their tokens, calls and prompts: the explainer's and
    the extractor's together."""
    logs = [log for log in (explanation.calls, texts.calls) if log]
    if not logs:
        return {
            "input_tokens": explanation.usage.input_tokens,
            "output_tokens": explanation.usage.output_tokens,
        }

    def total(a: int | None, b: int) -> int | None:
        return None if a is None and not b else (a or 0) + b

    return {
        "model_id": (explanation.calls and explainer_model)
        or (texts.calls and extractor_model)
        or None,
        "input_tokens": total(explanation.usage.input_tokens, texts.input_tokens),
        "output_tokens": total(explanation.usage.output_tokens, texts.output_tokens),
        "model_calls": tuple(c for log in logs for c in log.calls),
        "prompts": {k: v for log in logs for k, v in log.prompts.items()},
    }


def no_policy_found(found: FirstSearch, texts: TextReadings) -> AgentResult:
    """No registry had a record of any actor, and no policy text was read."""
    return abstain(
        ReasonCode.NO_CANDIDATES_RETRIEVED,
        f"No registry ({'; '.join(found.labels())}) has a policy record for "
        f"{', '.join(actor.name for actor, _ in found.searched)}. Many institutions have none; "
        "check the policies directly, including whether they require a particular repository."
        + texts.note
        + found.ror.note
        + opf_note(found),
    )


def mandated(advised: Advised) -> dict[str, RepositoryRef]:
    """The repositories FAIRsharing's records say a matched policy requires."""
    out: dict[str, RepositoryRef] = {}
    for item, _ in advised:
        if isinstance(item.record, PolicyRecord):
            for ref in assess.mandated(item.record):
                out.setdefault(ref.name.casefold(), ref)
    return out


def named_repositories(advised: Advised) -> list[str]:
    """The repositories a model read a policy's text as requiring, each quoted."""
    return sorted(
        {
            o.value
            for item, _ in advised
            for o in item.obligations
            if o.kind.value == "repository"
            and o.strength == Strength.REQUIRED
            and o.derivation == Derivation.MODEL
            and o.value
        }
    )


def conflicts(advised: Advised) -> list[PolicyConflict]:
    """Obligations the matched policies state differently, each grounded on its records."""
    stated: dict[str, assess.Stated] = {}
    for item, _ in advised:
        held = stated.get(item.record.source_id)
        obligations = (*held.obligations, *item.obligations) if held else item.obligations
        stated[item.record.source_id] = assess.Stated(item.record, obligations)
    return [
        PolicyConflict(
            kind=kind,
            description=description,
            grounded_on=[record_ref(r) for r in involved],
        )
        for kind, involved, description in assess.conflicts(list(stated.values()))
    ]


def _policies(advised: Advised) -> list[MatchedPolicy]:
    return [
        MatchedPolicy(
            actor=item.actor.name,
            role=item.actor.role,
            registry=_registry(item.record),
            match_derivation=item.matched_by,
            obligations=list(item.obligations),
            notes=list(item.notes),
            rationale=rationale.text,
            rationale_derivation=rationale.derivation,
            grounded_on=[record_ref(item.record)],
        )
        for item, rationale in advised
    ]


@dataclass
class Report:
    """The parts of the result both a matched and an unmatched run share."""

    found: FirstSearch
    texts: TextReadings
    explanation: Explanation
    advised: Advised
    use: dict[str, Any]

    def __post_init__(self) -> None:
        self.labels = self.found.labels()
        self.funders = self.found.funders()
        self.journals = self.found.resolved_journals()
        self.unresolved = self.found.unresolved()
        self.no_record = [
            actor.name
            for actor, _ in self.found.searched
            if not any(item.actor.name == actor.name for item, _ in self.advised)
        ]
        # The journals' records are cited whether or not a policy was matched.
        self.cited: dict[str, SourceRecord] = {}
        for jr in self.journals + [u for u in self.unresolved if u.role == ActorRole.JOURNAL]:
            for grounding in jr.grounded_on:
                if grounding.source_id in self.found.records:
                    self.cited[grounding.source_id] = self.found.records[grounding.source_id]

    def result(self) -> AgentResult:
        if not self.advised:
            # No policy, but ROR identified a funder, a journal was identified, or there are
            # candidates to choose from: the payload carries them, grounded on their records.
            return self._build(self._unmatched_statement(), {})
        fields: dict[str, Any] = {
            "policies": _policies(self.advised),
            "conflicts": conflicts(self.advised),
            "mandated_repositories": list(mandated(self.advised).values()),
        }
        statement = self._matched_statement(fields["policies"], fields["conflicts"])
        for item, _ in self.advised:
            self.cited[item.record.source_id] = item.record
        return self._build(statement, fields)

    def _build(self, statement: str, fields: dict[str, Any]) -> AgentResult:
        found = self.found
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=PolicyChecks(
                **fields,
                no_record=self.no_record,
                funders=self.funders,
                journals=self.journals,
                readings=self.texts.readings,
                ambiguous=self.unresolved,
                limitations=list(LIMITATIONS),
                searched=SearchedSummary(
                    queries=found.queries(),
                    snapshot_ref="; ".join(self.labels),
                    policies_retrieved=len({item.record.source_id for item, _ in self.advised}),
                ),
                grounded_on=[record_ref(r) for _, r in sorted(self.cited.items())]
                + [org_ref(o) for _, o in sorted(found.organisations.items())]
                + self.texts.refs,
            ),
            evidence=self._evidence(),
            **self.use,
        )

    def _evidence(self) -> list[EvidenceItem]:
        return (
            record_evidence(self.cited, self.found.registry_labels())
            + org_evidence(self.found.organisations, self.found.ror.where or "")
            + self.texts.evidence
        )

    def _identified(self) -> str:
        resolved = self.found.resolved
        out = (
            " Funders identified in ROR: "
            + "; ".join(f"{actor.name!r} as {_candidate(org)}" for actor, org in resolved)
            + f" ({self.found.ror.where})."
            if resolved
            else ""
        )
        if self.journals:
            out += (
                " Journals identified: "
                + "; ".join(
                    f"{j.actor!r}, published by {j.publisher or 'a publisher not named'}"
                    for j in self.journals
                )
                + "."
            )
        return out

    def _questions(self) -> str:
        questions = " ".join(
            [_ambiguity(actor, candidates) for actor, candidates in self.found.ambiguous]
            + [
                _journal_ambiguity(actor, candidates)
                for actor, candidates in self.found.ambiguous_journals
            ]
        )
        return " " + questions if questions else ""

    def _tail(self) -> str:
        """The notes on what was not searched or read, the model's remarks, and the call for a
        person to review."""
        remarks = " ".join(self.explanation.remarks)
        tail = self.texts.note + self.found.ror.note + opf_note(self.found)
        if remarks:
            tail += " " + remarks
        return tail + " Human review is required."

    def _unmatched_statement(self) -> str:
        statement = "No policy record was matched." + self._identified() + self._questions()
        if self.no_record:
            statement += (
                f" No registry ({'; '.join(self.labels)}) has a policy record for "
                f"{', '.join(self.no_record)}; check their policies directly, including whether "
                "they require a particular repository."
            )
        return statement + self._tail()

    def _matched_statement(
        self, policies: list[MatchedPolicy], found_conflicts: list[PolicyConflict]
    ) -> str:
        advised = self.advised
        actors_matched = len({item.actor.name for item, _ in advised})
        by_model = sum(1 for item, _ in advised if item.matched_by == Derivation.MODEL)
        quoted = sum(
            1 for item, _ in advised for o in item.obligations if o.derivation == Derivation.MODEL
        )
        registries = sorted({item.record.registry for item, _ in advised})
        statement = (
            f"Policies matched: {len(policies)} for {actors_matched} of "
            f"{len(self.found.actors)} actor(s), "
            f"from {' and '.join(registries)} ({'; '.join(self.labels)})."
        )
        if by_model:
            statement += f" Of these, {by_model} were found by a model with its search tools."
        if quoted:
            statement += (
                f" Obligations read from the records' text by a model: {quoted}, each with a "
                "quote found in its record."
            )
        statement += self._identified() + self._questions()
        if found_conflicts:
            statement += (
                f" Obligations the policies state differently: {len(found_conflicts)}; a person "
                "should decide which applies."
            )
        statement += self._repositories()
        if self.no_record:
            statement += (
                f" No policy record for: {', '.join(self.no_record)}; what they require, including "
                "any required repository, was not checked."
            )
        return statement + self._tail()

    def _repositories(self) -> str:
        """Which repositories the policies require, or that none was found to be."""
        required = mandated(self.advised)
        named = named_repositories(self.advised)
        out = ""
        if required:
            out += " Repositories required: " + ", ".join(r.name for r in required.values())
            out += "."
        if named:
            out += (
                " Repositories a policy's text requires, as a model read it (quoted in the "
                "obligations): " + "; ".join(named) + "."
            )
        read_required = any(
            o.kind.value == "repository" and o.strength == Strength.REQUIRED
            for r in self.texts.readings
            for o in r.stated
        )
        if not required and not named and not read_required:
            out += (
                " No matched record names a required repository. The registries' records do "
                "not always say which repositories a policy requires, so this is not evidence "
                "that none is required: check each policy's own text before choosing a "
                "repository."
            )
        return out
