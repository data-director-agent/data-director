"""advisor.linking: the Linking Adviser persona (docs/specs/agents.md).

Serves `deposit.links` and `post.links`. It recognises the DOIs, ORCID iDs, ROR ids and grant
numbers a researcher wants to link a dataset to, checks their form, gives each its canonical https
form (R7) and suggests how to record it in DataCite metadata (R11). It produces linking metadata
for the researcher to review; registering the links stays with the researcher and the repository.

The adviser matches each identifier against `schemes.yaml` and checks an ORCID iD's checksum, and
calls no model. Where the harness grants it a DOI-lookup tool, it also looks each well-formed DOI up
through the tool gateway (`resolve.py`) and cites the record it found. ORCID iDs, ROR ids and grant
numbers are checked by form only; resolving them is TODO(#360).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from dd_agent_advisor_linking import resolve
from dd_agent_advisor_linking.classes import LinkCandidates, RelatedIdentifiers, RelatedLink
from dd_sdk import serve
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
    "ORCID iDs, ROR ids and grant numbers are checked by form only and were not resolved, so a "
    "well-formed one may not exist or may name something else.",
    "It does not look up names, funders or relations in ORCID, ROR or funder services.",
    "Its relation suggestions are defaults by scheme, not read from what the identifier names.",
    "It recognises DOIs, ORCID iDs, ROR ids and grant numbers only; other identifiers, such as "
    "arXiv ids, software heritage ids or accession numbers, are reported as unknown.",
)
DOIS_NOT_RESOLVED = (
    "DOIs were checked by form only and not resolved: no DOI-lookup tool was available, so a "
    "well-formed DOI may not exist or may name something else."
)
DOIS_RESOLVED = (
    "DOIs were looked up through the tool gateway where a record was found; one marked not "
    "resolved was not found or could not be looked up, and is recorded by form only."
)
INVALID_ORCID = (
    "The final character is not the ORCID checksum of the other digits: check the iD for a typing "
    "error."
)
UNKNOWN_MESSAGE = (
    "Not recognised as a DOI, ORCID iD, ROR id or grant number. Give it in one of those forms, or "
    "record it by hand."
)


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
        version="0.2.0a1",
        title="Linking Adviser",
        icon="🔗",
        description=(
            "Recognises DOIs, ORCID iDs, ROR ids and grant numbers, checks their form, gives "
            "their canonical https form and suggests how to record each link. Looks DOIs up "
            "through the tool gateway where one is granted; the other identifiers are checked by "
            "form only. The researcher and the repository register the links."
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
            "links.message": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("deposit.links", "post.links"),
        tools=resolve.TOOLS,
    )

    def __init__(self, schemes: list[Scheme] | None = None) -> None:
        self.schemes = schemes if schemes is not None else load_schemes()

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
        server = resolve.doi_server(ctx.tools)
        records: list[ToolRecord] = []
        if ctx.tools is not None and server is not None:
            lookups = [
                resolve.lookup(ctx.tools, server, link)
                if link.scheme == "doi" and link.valid
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
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Recognised {recognised} of {len(links)} identifiers by form; resolved "
                    f"{found} through the tool gateway. The researcher reviews each link before "
                    "it is registered."
                ),
            ),
            payload=RelatedIdentifiers(
                links=links,
                limitations=[DOIS_RESOLVED if server else DOIS_NOT_RESOLVED, *LIMITATIONS],
                grounded_on=[r.ref() for r in records] or [input_ref(ctx)],
            ),
            evidence=[r.evidence() for r in records] or [input_evidence(ctx)],
        )

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


def build() -> LinkingAdviser:
    return LinkingAdviser()


def main() -> int:
    """The `dd-advisor-linking` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
