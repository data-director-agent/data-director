"""Test doubles that implement the retrieval and explainer protocols without production code."""

from __future__ import annotations

from workbench.agents.base import RunContext
from workbench.agents.r3.explain import Item, Rationale, Usage
from workbench.agents.r3.fairsharing.records import MODEL_AND_FORMAT, TERMINOLOGY, Record
from workbench.agents.r3.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef
from workbench.contract.models import DatasetProfile, Derivation
from workbench.tracing import chat_span

ISO8601 = Record(
    fairsharing_id="FAIRsharing.test-iso8601",
    doi="10.25504/FAIRsharing.test-iso8601",
    name="ISO 8601 Date and time format",
    abbreviation="ISO 8601",
    record_type=MODEL_AND_FORMAT,
    status="ready",
    description="International standard covering the exchange of date and time related data.",
    subjects=["Data Management", "Computer Science"],
)
AGROVOC = Record(
    fairsharing_id="FAIRsharing.test-agrovoc",
    doi="10.25504/FAIRsharing.test-agrovoc",
    name="AGROVOC Multilingual Thesaurus",
    abbreviation="AGROVOC",
    record_type=TERMINOLOGY,
    status="ready",
    description=(
        "A controlled vocabulary covering agriculture, forestry, fisheries, food and environment, "
        "including soil science."
    ),
    subjects=["Agriculture", "Soil science", "Environmental science"],
)
ENVO = Record(
    fairsharing_id="FAIRsharing.test-envo",
    doi="10.25504/FAIRsharing.test-envo",
    name="Environment Ontology",
    abbreviation="ENVO",
    record_type=TERMINOLOGY,
    status="ready",
    description=(
        "An ontology of environmental systems, components and processes, including soil horizons."
    ),
    subjects=["Environmental science", "Ecology"],
)
CSV = Record(
    fairsharing_id="FAIRsharing.test-csv",
    doi="10.25504/FAIRsharing.test-csv",
    name="Comma-separated values",
    abbreviation="CSV",
    record_type=MODEL_AND_FORMAT,
    status="ready",
    description="A tabular data format in which values are separated by commas.",
    subjects=["Data Management"],
)
DEPRECATED = Record(
    fairsharing_id="FAIRsharing.test-old",
    name="Old soil vocabulary",
    record_type=TERMINOLOGY,
    status="deprecated",
    description="A deprecated controlled vocabulary about soil.",
    subjects=["Soil science"],
)

ALL = [ISO8601, AGROVOC, ENVO, CSV, DEPRECATED]


class FakeRetrieval:
    """Substring matching over a fixed record list; enough to drive ranking and the linter."""

    def __init__(self, records: list[Record] | None = None, unavailable: bool = False) -> None:
        self.records = ALL if records is None else records
        self.unavailable = unavailable
        self.queries: list[Query] = []

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake")

    def search(self, query: Query) -> list[Hit]:
        self.queries.append(query)
        if self.unavailable:
            raise RegistryUnavailable("fake registry is down")
        words = [w.lower() for w in query.text.split()]
        hits: list[Hit] = []
        for r in self.records:
            if query.record_type and r.record_type != query.record_type:
                continue
            text = r.search_text().lower()
            score = sum(1.0 for w in words if w in text)
            if score > 0:
                hits.append(Hit(record=r, lexical_score=score))
        hits.sort(key=lambda h: -h.lexical_score)
        return hits[: query.limit]

    def fetch(self, fairsharing_id: str) -> Record | None:
        return next((r for r in self.records if r.fairsharing_id == fairsharing_id), None)


class FakeModelExplainer:
    """Emits a chat span like a real model would, and optionally an ungrounded identifier."""

    model_id: str | None = "fake-model"

    def __init__(self, hallucinate: bool = False) -> None:
        self.usage = Usage()
        self.hallucinate = hallucinate

    def explain(
        self, profile: DatasetProfile, items: list[Item], ctx: RunContext
    ) -> list[Rationale]:
        with chat_span(ctx.tracer, "fake-model"):
            self.usage = Usage(input_tokens=100, output_tokens=50)
        out = []
        for record, *_ in items:
            text = f"Model says {record.name} fits."
            if self.hallucinate:
                text += " See also FAIRsharing.made-up."
            out.append(Rationale(text, Derivation.MODEL))
        return out


class ChatBeforeRetrievalExplainer(FakeModelExplainer):
    """Used with a retrieval adapter that emits no spans, to violate G1 deliberately."""
