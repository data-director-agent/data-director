"""Stage 2 — retrieve (§5.2). Query building is real; the search returns nothing at v0.1.

§5.2 runs **four** searches, not one — one per kind of recommendation R3 owes, each sending
different filters and drawing on different parts of the profile. Those four query objects are
built for real here, because they are what an abstention reports as "what we searched for", and
because building them exercises the profile in the way the real stage will.

What is missing is a registry to ask. `EmptyRegistry` returns no records, so every kind ends up
in `nothing_found` — with the correct facets, which is the point. See `registry/fairsharing.py`
for why no live route is written yet.

Three things §5.2 says are not up for negotiation, and where each lands:

- **Subject and record-type lists come from the registry, not our code.** No list is hard-coded
  in this module. The record-type and subtype *filters* below are FAIRsharing's own registry
  vocabulary for record kinds, not a list of standards, and they are the fields §5.2 names for
  telling ontologies from vocabularies.
- **Every candidate remembers where it came from.** `RegistrySearchResult` carries the query and
  snapshot back, and `_to_candidate` copies both onto the candidate.
- **Status is kept, never quietly filtered out.** No status filter appears in any query. A
  deprecated standard a researcher is currently using is extremely useful information — as a
  warning — so the ranker penalises a record rather than the retriever hiding it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from standards_advisor.errors import RegistryUnavailable
from standards_advisor.models.candidates import Candidate, CandidateSet, RegistryQuery
from standards_advisor.models.common import (
    LifecyclePhase,
    RecommendationKind,
    StageName,
    StageStatus,
)
from standards_advisor.models.profile import ColumnType, DatasetProfile
from standards_advisor.models.recommendations import ResourceRef, Target, TargetKind
from standards_advisor.nodes.support import merge, stage
from standards_advisor.registry.base import RegistryRecord, RegistrySearchResult

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.state import PipelineState

# FAIRsharing's own record-type vocabulary, used as *filters* — not a list of standards. R3.5
# forbids a built-in list of standards; it does not forbid naming the registry's record kinds,
# which is how §5.2's table says each of the four searches is scoped.
TERMINOLOGY_RECORD_TYPE = "terminology_artefact"
MODEL_FORMAT_RECORD_TYPE = "model_and_format"
REPORTING_GUIDELINE_RECORD_TYPE = "reporting_guideline"

# The subtypes §5.2 uses to separate the two kinds R3 must distinguish. Read off the record
# rather than judged by a model — see the §1.2 stop condition on this.
ONTOLOGY_SUBTYPES = ("ontology",)

# Column types that imply a field-level standard is worth searching for (R3.4).
#
# `TIME`, `DURATION` and `BOOLEAN` are here because each has a real answer that researchers
# routinely get wrong — ISO 8601 covers times and durations, and how `true` and `false` are
# written down is a genuine interoperability question. They only ever arise from a declared
# dictionary type (§8); tier-1 inference does not produce them.
#
# `UNKNOWN` is deliberately absent, and `FREE_TEXT`, `NUMBER` and `EMPTY` remain so. There is no
# field-level standard for a column we could not map, and searching for one would produce advice
# that does not fit — which is the failure R3.6 exists to prevent.
FIELD_LEVEL_TYPES: frozenset[ColumnType] = frozenset(
    {
        ColumnType.DATE,
        ColumnType.DATETIME,
        ColumnType.TIME,
        ColumnType.DURATION,
        ColumnType.COORDINATE,
        ColumnType.QUANTITY_WITH_UNIT,
        ColumnType.IDENTIFIER,
        ColumnType.CATEGORICAL,
        ColumnType.BOOLEAN,
    }
)


def retrieve_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    profile = state.get("profile")

    with stage(ctx, StageName.RETRIEVE) as run:
        if profile is None:
            run.status = StageStatus.EMPTY
            run.fail("no_profile", "retrieve ran with no profile; nothing to search for")
            run.payload = CandidateSet(
                queries=[],
                candidates=[],
                snapshot=ctx.registry.snapshot(),
                unavailable_kinds=list(RecommendationKind),
            )
            return_value = run.payload
        else:
            queries = build_queries(profile)
            candidates: list[Candidate] = []
            unavailable: list[RecommendationKind] = []

            for query in queries:
                try:
                    result = ctx.registry.search(query)
                except RegistryUnavailable as exc:
                    unavailable.append(query.kind)
                    run.fail("registry_unavailable", f"{query.kind}: {exc}")
                    continue
                candidates.extend(_to_candidates(result))

            run.payload = CandidateSet(
                queries=queries,
                candidates=candidates,
                snapshot=ctx.registry.snapshot(),
                unavailable_kinds=unavailable,
            )
            run.counts = {"queries": len(queries), "candidates": len(candidates)}
            if not candidates:
                run.status = StageStatus.EMPTY
                run.note(
                    f"no candidates from registry route {ctx.registry_route!r}; "
                    "every kind will be reported in nothing_found"
                )
            return_value = run.payload

    return merge(run, candidates=return_value)


def build_queries(profile: DatasetProfile) -> list[RegistryQuery]:
    """The four §5.2 searches, one per kind of recommendation R3 owes."""
    subjects = [term.term for term in profile.subjects]
    domains = [term.term for term in profile.fields_of_research]
    entities = [term.term for term in profile.entity_scope]
    facets = {
        "subject": subjects,
        "domain": domains,
        "entity_scope": entities,
    }

    return [
        _vocabulary_query(profile, facets),
        _ontology_query(profile, facets),
        _format_query(profile, facets),
        _field_level_query(profile),
    ]


def _vocabulary_query(profile: DatasetProfile, facets: dict[str, list[str]]) -> RegistryQuery:
    """R3.1 — terminology resources, *excluding* the ontology subtypes.

    Targets the columns whose values could be pinned to concept identifiers: categorical
    columns first, since those are the ones with a small closed set of values. Pre-collection
    that set is *declared* rather than sampled, which is a stronger signal — a dictionary's
    enumeration is every value the column may take, not the ones that happened to appear in the
    head of a file.
    """
    targets = [
        Target(kind=_field_target_kind(profile), field=column.name, file=column.file)
        for column in profile.columns
        if column.inferred_type == ColumnType.CATEGORICAL
    ]
    return RegistryQuery(
        kind=RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE,
        record_types=[TERMINOLOGY_RECORD_TYPE],
        exclude_subtypes=list(ONTOLOGY_SUBTYPES),
        facets=dict(facets),
        free_text=profile.title,
        targets=targets,
    )


def _ontology_query(profile: DatasetProfile, facets: dict[str, list[str]]) -> RegistryQuery:
    """R3.2 — terminology resources, ontology subtypes *only*.

    Targets the dataset's structure rather than any column's values (§2.1), and additionally
    draws on measured variables, per §5.2's table.
    """
    variables = [variable.name for variable in profile.measured_variables]
    return RegistryQuery(
        kind=RecommendationKind.ONTOLOGY_ALIGNMENT,
        record_types=[TERMINOLOGY_RECORD_TYPE],
        include_subtypes=list(ONTOLOGY_SUBTYPES),
        facets={**facets, "measured_variable": variables},
        free_text=profile.abstract,
        targets=[
            Target(
                kind=TargetKind.STRUCTURE,
                detail=f"{len(profile.columns)} variables across {len(profile.files)} file(s)",
            )
        ],
    )


def _format_query(profile: DatasetProfile, facets: dict[str, list[str]]) -> RegistryQuery:
    """R3.3 — models and formats, for the formats found in the input or planned for it.

    The two are kept in separate facets rather than merged. "You wrote XLSX, here is an open
    alternative" and "you plan to write XLSX, here is what to write instead" are different
    recommendations, and an abstention has to be able to say which question it failed to answer.
    """
    return RegistryQuery(
        kind=RecommendationKind.OPEN_FORMAT,
        record_types=[MODEL_FORMAT_RECORD_TYPE],
        facets={
            **facets,
            "format": list(profile.formats_found),
            "format_planned": list(profile.formats_planned),
        },
        targets=(
            [
                Target(kind=TargetKind.FILE, file=entry.path, detail=entry.format)
                for entry in profile.files
            ]
            or [
                Target(kind=TargetKind.DATASET, detail=f"planned format {fmt}")
                for fmt in profile.formats_planned
            ]
        ),
    )


def _field_level_query(profile: DatasetProfile) -> RegistryQuery:
    """R3.4 — how values are written, driven entirely by the inferred column types.

    This is the query tier-1 profiling was built to enable, and the one that should work first
    once a registry route exists: its inputs are mechanical and already present.
    """
    interesting = [
        column for column in profile.columns if column.inferred_type in FIELD_LEVEL_TYPES
    ]
    return RegistryQuery(
        kind=RecommendationKind.FIELD_LEVEL_STANDARD,
        record_types=[MODEL_FORMAT_RECORD_TYPE, REPORTING_GUIDELINE_RECORD_TYPE],
        facets={
            "column_type": sorted({column.inferred_type.value for column in interesting}),
            "unit": sorted({column.unit for column in interesting if column.unit}),
        },
        targets=[
            Target(
                kind=_field_target_kind(profile),
                field=column.name,
                file=column.file,
                detail=f"{column.inferred_type.value}"
                + (f" ({column.pattern})" if column.pattern else ""),
            )
            for column in interesting
        ],
    )


def _field_target_kind(profile: DatasetProfile) -> TargetKind:
    """What a column-level recommendation applies to, given the run's phase.

    Pre-collection there are no values yet, so `FIELD_VALUES` would be a claim about data that
    does not exist. The distinction is not cosmetic: it is the difference between advice that
    means "migrate what you have" and advice that means "decide this before you start", and the
    reader cannot recover it from anything else in the recommendation.
    """
    if profile.phase is LifecyclePhase.PRE_COLLECTION:
        return TargetKind.PLANNED_VARIABLE
    return TargetKind.FIELD_VALUES


def _to_candidates(result: RegistrySearchResult) -> list[Candidate]:
    return [_to_candidate(result, record) for record in result.records]


def _to_candidate(result: RegistrySearchResult, record: RegistryRecord) -> Candidate:
    """Wrap a record as a candidate, keeping the query and snapshot that found it (§5.2)."""
    return Candidate(
        kind=result.query.kind,
        resource=ResourceRef(
            name=record.name,
            registry_id=record.registry_id,
            doi=record.doi,
            url=record.url,
            record_type=record.record_type,
            record_subtype=record.record_subtype,
            status=record.status,
        ),
        query=result.query,
        snapshot=result.snapshot,
        populated_fields=sorted(record.populated_fields),
        record=dict(record.fields),
        targets=list(result.query.targets),
    )
