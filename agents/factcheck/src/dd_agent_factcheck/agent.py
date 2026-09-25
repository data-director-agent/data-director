"""fact.checker: a verdict on a Claim, grounded on the sources it consulted.

A retrieval-mode agent that is not R3: it retrieves records from a `SourceIndex` (by default a
small packaged `sources.json`), emits one `retrieval` span per source consulted, and returns a
`FactCheck` whose `grounded_on` names exactly those sources. It calls no model; the verdict is a
lexical rule and says so (`rationale_derivation: template`).

The rule is naive by design — it exists to exercise the harness, not to check facts. A source
sentence that contains every content word of the claim *supports* it when both or neither
contain a negation, and *refutes* it when exactly one does; a claim no sentence covers is
*unverifiable* against the sources consulted. TODO: a real fact-checking agent would retrieve
from a maintained corpus and use a model to judge entailment after retrieval.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.models import (
    Claim,
    Derivation,
    EvidenceItem,
    FactCheck,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Verdict,
)
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash
from dd_sdk.tracing import retrieval_span

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"

STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "of", "to", "in", "on",
        "for", "and", "or", "as", "by", "at", "it", "its", "this", "that", "with", "from",
    }
)  # fmt: skip
NEGATIONS = frozenset({"not", "no", "never", "cannot", "without"})
MIN_OVERLAP = 2  # content words a source must share with the claim to count as consulted


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    text: str
    uri: str | None = None

    def document(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "text": self.text,
            "uri": self.uri,
        }

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)


class SourceIndex(Protocol):
    def search(self, words: set[str]) -> list[Source]: ...


class InMemorySources:
    def __init__(self, sources: list[Source]) -> None:
        self.sources = sources

    @classmethod
    def from_file(cls, path: Path = SOURCES) -> InMemorySources:
        return cls([Source(**s) for s in json.loads(path.read_text(encoding="utf-8"))])

    def search(self, words: set[str]) -> list[Source]:
        hits = []
        for s in self.sources:
            overlap = len(words & _words(s.title + " " + s.text))
            if overlap >= MIN_OVERLAP:
                hits.append((overlap, s))
        hits.sort(key=lambda h: (-h[0], h[1].source_id))
        return [s for _, s in hits]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower()) if w not in STOPWORDS}


def _judge(claim_words: set[str], source: Source) -> Verdict:
    content = claim_words - NEGATIONS
    claim_negated = bool(claim_words & NEGATIONS)
    for sentence in re.split(r"(?<=[.!?])\s+", source.text):
        words = _words(sentence)
        if content <= words:
            negated = bool(words & NEGATIONS)
            return Verdict.REFUTED if negated != claim_negated else Verdict.SUPPORTED
    return Verdict.UNVERIFIABLE


class FactChecker:
    spec = AgentSpec(
        agent_id="fact.checker",
        version="0.1.0",
        description="Gives a lexical verdict on a claim, grounded on the sources it retrieved.",
        requirement_ids=("DD-GROUNDING",),
        action_class="advise",
        accepts=(Claim,),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload_type=FactCheck,
        derivations={
            "verdict": Derived(Derivation.LEXICAL),
            "rationale": Derived(Derivation.TEMPLATE, recorded_in="rationale_derivation"),
        },
    )

    def __init__(self, sources: SourceIndex | None = None) -> None:
        self.sources = sources or InMemorySources.from_file()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        claim = request.input
        assert isinstance(claim, Claim)  # the conductor checked spec.accepts
        words = _words(claim.text)
        if len(words) < MIN_OVERLAP:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="The claim has too few content words to search on.",
                )
            )
        consulted = self.sources.search(words)
        # One retrieval span per source consulted: this is what the verdict may rest on.
        for source in consulted:
            with retrieval_span(ctx.tracer, source.source_id, source.content_hash()):
                pass
        if not consulted:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.NO_CANDIDATES_RETRIEVED,
                    statement=(
                        f"No source shares {MIN_OVERLAP} or more content words with the claim."
                    ),
                )
            )

        verdicts = {s.source_id: _judge(words, s) for s in consulted}
        if Verdict.REFUTED in verdicts.values():
            verdict = Verdict.REFUTED
        elif Verdict.SUPPORTED in verdicts.values():
            verdict = Verdict.SUPPORTED
        else:
            verdict = Verdict.UNVERIFIABLE
        deciding = [sid for sid, v in verdicts.items() if v == verdict] or list(verdicts)
        rationale = (
            f"{verdict.value.capitalize()} by lexical match against {', '.join(deciding)} "
            f"({len(consulted)} source(s) consulted). The rule checks word overlap and negation, "
            "not meaning."
        )
        now = datetime.now(UTC)
        refs = [
            GroundingRef(source_id=s.source_id, content_hash=s.content_hash()) for s in consulted
        ]
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=f"Verdict {verdict.value}, grounded in {len(consulted)} retrieved "
                "source(s). Human review is required.",
            ),
            payload=FactCheck(
                verdict=verdict,
                rationale=rationale,
                rationale_derivation=Derivation.TEMPLATE,
                grounded_on=refs,
            ),
            evidence=[
                EvidenceItem(
                    source_id=s.source_id,
                    source_uri=s.uri,
                    retrieved_at=now,
                    snapshot_ref="packaged:sources.json",
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=DOCUMENT_CANONICALISATION,
                    content_hash=s.content_hash(),
                )
                for s in consulted
            ],
        )


def build() -> FactChecker:
    return FactChecker()


def main() -> int:
    """Console script: serve this agent over A2A (`dd_sdk.serve`)."""
    return serve.main(build)
