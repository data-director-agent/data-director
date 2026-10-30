"""advisor.linking: the Linking Adviser persona (ADR-0033). A mock.

Serves `deposit.links` and `post.links`. It recognises the DOIs, ORCID iDs, ROR ids and grant
numbers a researcher wants to link a dataset to, checks their form, gives each its canonical https
form (R7) and suggests how to record it in DataCite metadata (R11). It produces linking metadata
for the researcher to review; registering the links stays with the researcher and the repository.

The mock matches each identifier against `schemes.yaml` and checks an ORCID iD's checksum. It
resolves nothing, consults no source and calls no model, so its grounding mode is `none` and it
cites only its input. The real adviser, which resolves identifiers through DOI, Crossref,
DataCite, ORCID, ROR and funder services, is TODO(#360).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dd_agent_advisor_linking.classes import LinkCandidates, RelatedIdentifiers, RelatedLink
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

SCHEMES = Path(__file__).with_name("schemes.yaml")
UNKNOWN = "unknown"

LIMITATIONS = (
    "This is a mock: it checks only the form of each identifier and resolved none of them, so a "
    "well-formed identifier may not exist or may name something else.",
    "It does not look up titles, names, funders or relations in DOI, Crossref, DataCite, ORCID, "
    "ROR or funder services.",
    "Its relation suggestions are defaults by scheme, not read from what the identifier names.",
    "It recognises DOIs, ORCID iDs, ROR ids and grant numbers only; other identifiers, such as "
    "arXiv ids, software heritage ids or accession numbers, are reported as unknown.",
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
        version="0.1.0a1",
        title="Linking Adviser",
        description=(
            "Mock. Recognises DOIs, ORCID iDs, ROR ids and grant numbers, checks their form, gives "
            "their canonical https form and suggests how to record each link. Resolves nothing; "
            "the researcher and the repository register the links."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(LinkCandidates),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(RelatedIdentifiers),
        derivations={
            "links.scheme": Derived(Derivation.LEXICAL),
            "links.normalised": Derived(Derivation.LEXICAL),
            "links.relation": Derived(Derivation.TEMPLATE),
            "links.valid": Derived(Derivation.LEXICAL),
            "links.message": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("deposit.links", "post.links"),
    )

    def __init__(self, schemes: list[Scheme] | None = None) -> None:
        self.schemes = schemes if schemes is not None else load_schemes()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        candidates = request.input
        assert isinstance(candidates, LinkCandidates)  # the conductor checked spec.accepts
        given = [g.strip() for g in candidates.identifiers if g.strip()]
        if not given:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement=(
                        "Give the identifiers to link: DOIs, ORCID iDs, ROR ids or grant numbers."
                    ),
                )
            )

        links = [self._link(g) for g in given]
        recognised = sum(link.scheme != UNKNOWN for link in links)
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: recognised {recognised} of {len(links)} identifiers by form; none was "
                    "resolved. The researcher reviews each link before it is registered."
                ),
            ),
            payload=RelatedIdentifiers(
                links=links,
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
                message=f"Recognised by form only, not resolved. {scheme.advice}",
            )
        return RelatedLink(given=given, scheme=UNKNOWN, valid=False, message=UNKNOWN_MESSAGE)


def build() -> LinkingAdviser:
    return LinkingAdviser()


def main() -> int:
    """The `dd-advisor-linking` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
