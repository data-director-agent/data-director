"""advisor.linking: the Linking Adviser persona (docs/specs/agents.md).

Serves `deposit.links` and `post.links`. It recognises the DOIs, ORCID iDs, ROR ids and grant
numbers a researcher wants to link a dataset to, checks their form, gives each its canonical https
form (R7) and suggests how to record it in DataCite metadata (R11). It produces linking metadata
for the researcher to review; registering the links stays with the researcher and the repository.

The adviser matches each identifier against `schemes.yaml` and checks an ORCID iD's checksum. Where
the harness grants it lookup tools, it also looks each well-formed DOI, ORCID iD, ROR id and grant
number up through the tool gateway (`resolve.py`: DataCite then Crossref, ORCID, ROR, and the
grant resolver) and cites the record it found, suggesting a DOI's relation from the type of work
its record names (`relations.yaml`). A grant number may name several funders' grants: each is
listed as a candidate and cited, and the researcher chooses (`grants.py`). Each
link is decided by rule; a summariser (`dd_sdk.summary`) then writes a short summary beside them:
a model's by default, the rules' own with `DD_LINKING_SUMMARISER=template` (`factory.py`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from dd_agent_advisor_linking import resolve
from dd_agent_advisor_linking.classes import LinkCandidates, RelatedIdentifiers, RelatedLink
from dd_sdk import summary
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
from dd_sdk.tools import ToolRecord
from dd_sdk.tracing import retrieval_span

SCHEMES = Path(__file__).with_name("schemes.yaml")
UNKNOWN = "unknown"

LIMITATIONS = (
    "A grant number is looked up by the number alone, without its funder, so a number that "
    "several funders use lists each of their grants for the researcher to choose from; the "
    "adviser does not choose.",
    "It does not look up the relations between works; a resolved record says what an identifier "
    "names, not how it relates to the dataset.",
    "A DOI's relation is suggested from the type of work its record names; one not resolved, or "
    "of a type the adviser does not know, is given IsSupplementTo by default. Either way it is a "
    "suggestion for the researcher to confirm.",
    "It recognises DOIs, ORCID iDs, ROR ids and grant numbers only; other identifiers, such as "
    "arXiv ids, software heritage ids or accession numbers, are reported as unknown.",
    "Its summary is written by a model from the findings alone unless the template is chosen; "
    "the links above it are the adviser's findings, not the summary.",
)
NOT_RESOLVED = (
    "{schemes} were checked by form only and not resolved: no lookup tool for them was "
    "available, so a well-formed one may not exist or may name something else."
)
RESOLVED = (
    "{schemes} were looked up through the tool gateway; one marked not resolved was not found or "
    "could not be looked up, and is recorded by form only."
)
INVALID_ORCID = (
    "The final character is not the ORCID checksum of the other digits: check the iD for a typing "
    "error."
)
UNKNOWN_MESSAGE = (
    "Not recognised as a DOI, ORCID iD, ROR id or grant number. Give it in one of those forms, or "
    "record it by hand."
)


def _joined(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"


@dataclass(frozen=True)
class Scheme:
    name: str
    pattern: re.Pattern[str]
    prefix: str | None
    relation: str | None
    advice: str


def load_schemes(path: Path = SCHEMES) -> list[Scheme]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return [
        Scheme(
            name=str(name),
            pattern=re.compile(str(rule["pattern"]), re.IGNORECASE),
            prefix=rule.get("prefix"),
            relation=rule.get("relation"),
            advice=" ".join(str(rule["advice"]).split()),
        )
        for name, rule in table.items()
    ]


def orcid_checksum_ok(orcid: str) -> bool:
    """Whether an ORCID iD's last character is the ISO 7064 MOD 11-2 check of its 15 digits."""
    digits = orcid.replace("-", "").upper()
    total = 0
    for d in digits[:-1]:
        total = (total + int(d)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


class LinkingAdviser:
    spec = AgentSpec(
        agent_id="advisor.linking",
        version="0.3.0a1",
        title="Linking Adviser",
        icon="🔗",
        description=(
            "Recognises DOIs, ORCID iDs, ROR ids and grant numbers, checks their form, gives "
            "their canonical https form and suggests how to record each link. Looks each up "
            "through the tool gateway where it is granted, and lists every grant a grant number "
            "may name for the researcher to choose from. Summarises what to do. The researcher "
            "and the repository register the links."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(LinkCandidates),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(RelatedIdentifiers),
        derivations={
            "links.scheme": Derived(Derivation.LEXICAL),
            "links.normalised": Derived(Derivation.LEXICAL),
            "links.relation": Derived(Derivation.TEMPLATE),
            "links.valid": Derived(Derivation.LEXICAL),
            "links.resolved": Derived(Derivation.REGISTRY),
            "links.title": Derived(Derivation.REGISTRY),
            "links.resource_type": Derived(Derivation.REGISTRY),
            "links.candidates": Derived(Derivation.REGISTRY),
            "links.message": Derived(Derivation.TEMPLATE),
            "summary": Derived(Derivation.MODEL, recorded_in="summary_derivation"),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("deposit.links", "post.links"),
        tools=resolve.TOOLS,
    )

    def __init__(
        self, schemes: list[Scheme] | None = None, summariser: summary.Summariser | None = None
    ) -> None:
        self.schemes = schemes if schemes is not None else load_schemes()
        self.summariser = summariser or summary.TemplateSummariser()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        candidates = request.input
        assert isinstance(candidates, LinkCandidates)  # the conductor checked spec.accepts
        given = [g.strip() for g in candidates.identifiers if g.strip()]
        if not given:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Give the identifiers to link: DOIs, ORCID iDs, ROR ids or grant numbers.",
            )

        links = [self._link(g) for g in given]
        routes = resolve.available(ctx.tools)
        records: list[ToolRecord] = []
        if ctx.tools is not None and routes:
            lookups = [
                resolve.lookup(ctx.tools, routes[link.scheme], link)
                if link.valid and link.scheme in routes
                else resolve.Lookup(link)
                for link in links
            ]
            links = [lk.link for lk in lookups]
            records = resolve.cited(lookups)
        if not records:
            # Nothing was looked up, so the payload rests on the input alone, which the agent read
            # itself: in retrieval mode a cited record must have a retrieval span (G2).
            with retrieval_span(ctx.tracer, ctx.input_ref, ctx.input_hash):
                pass
        recognised = sum(link.scheme != UNKNOWN for link in links)
        found = sum(link.resolved is True for link in links)
        statement = (
            f"Recognised {recognised} of {len(links)} identifiers by form; resolved "
            f"{found} through the tool gateway. The researcher reviews each link before "
            "it is registered."
        )
        looked_up = [r.label for r in resolve.ROUTES if r.scheme in routes]
        form_only = [r.label for r in resolve.ROUTES if r.scheme not in routes]
        told = summary.Findings(
            {"links": [link.model_dump(mode="json", exclude_none=True) for link in links]},
            statement,
        )
        summarised, explanation = summary.summarise(self.summariser, told, ctx)
        result = AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=RelatedIdentifiers(
                links=links,
                summary=summarised.text,
                summary_derivation=summarised.derivation,
                limitations=[
                    *([RESOLVED.format(schemes=_joined(looked_up))] if looked_up else []),
                    *([NOT_RESOLVED.format(schemes=_joined(form_only))] if form_only else []),
                    *LIMITATIONS,
                ],
                grounded_on=[r.ref() for r in records] or [input_ref(ctx)],
            ),
            evidence=[r.evidence() for r in records] or [input_evidence(ctx)],
        )
        return summary.with_calls(result, self.summariser.model_id, explanation)

    def _link(self, given: str) -> RelatedLink:
        for scheme in self.schemes:
            match = scheme.pattern.fullmatch(given)
            if match is None:
                continue
            ident = match.group(1)
            if scheme.name == "orcid":
                ident = ident.upper()
                if not orcid_checksum_ok(ident):
                    return RelatedLink(
                        given=given, scheme=scheme.name, valid=False, message=INVALID_ORCID
                    )
            elif scheme.name == "ror":
                ident = ident.lower()
            return RelatedLink(
                given=given,
                scheme=scheme.name,
                normalised=f"{scheme.prefix}{ident}" if scheme.prefix else None,
                relation=scheme.relation,
                valid=True,
                message=f"{resolve.FORM_ONLY} {scheme.advice}",
            )
        return RelatedLink(given=given, scheme=UNKNOWN, valid=False, message=UNKNOWN_MESSAGE)
