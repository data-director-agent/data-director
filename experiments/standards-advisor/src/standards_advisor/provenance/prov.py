"""Building the §6.3 PROV-O graph from a run manifest and its event log.

Built from `run.json` plus `events.jsonl` — never by reading the checkpoint database. The
provenance record must not depend on a dependency's storage format, which is the same reason
the run directory exists at all (see `run_dir`).
"""

from __future__ import annotations

from standards_advisor.models.common import StageName
from standards_advisor.models.provenance import (
    EnergyEstimate,
    ProvActivity,
    ProvAgent,
    ProvDocument,
    ProvEntity,
)
from standards_advisor.provenance.manifest import RunManifest
from standards_advisor.provenance.run_dir import RUN_FILES


def _uri(run_id: str, *parts: str) -> str:
    return "urn:dd:r3:" + ":".join([run_id, *parts])


def _primary_input(
    stage: str,
    input_entity: str,
    registry_entity: str,
    intake_entity: str | None,
) -> str:
    """The main entity a stage consumed.

    A table rather than a chain of conditionals because it is a mapping, and because a stage
    added without an entry here would otherwise be quietly attributed to the dataset input —
    claiming it read something it never touched, in the one record whose whole purpose is to be
    accurate about that.
    """
    if stage == StageName.ELICIT:
        # The question set is what `elicit` consumes; the answers are what it produces.
        return intake_entity or input_entity
    if stage in {StageName.RETRIEVE, StageName.RANK}:
        return registry_entity
    return input_entity


def build_prov_document(manifest: RunManifest, token_totals: dict[str, int]) -> ProvDocument:
    """Assemble the graph for one run."""
    run_id = manifest.run_id
    nodes: list[ProvEntity | ProvActivity | ProvAgent] = []

    software_agent = _uri(run_id, "agent", "software")
    nodes.append(
        ProvAgent(
            id=software_agent,
            type=["prov:Agent", "prov:SoftwareAgent"],
            label=manifest.agent.identity,
            dd_version=manifest.agent.version,
        )
    )

    # The model is its own agent. Attaching it to the run as a whole would lose which stage it
    # influenced, which is exactly what §6.3 asks to be recorded.
    model_agent = _uri(run_id, "agent", "model")
    nodes.append(
        ProvAgent(
            id=model_agent,
            type=["prov:Agent", "prov:SoftwareAgent"],
            label=manifest.model.model_id,
            dd_model_params=manifest.model.params or None,
        )
    )

    # -- entities ------------------------------------------------------------------------

    input_entity = _uri(run_id, "entity", "input")
    nodes.append(
        ProvEntity(
            id=input_entity,
            type="prov:Entity",
            label="dataset input",
            dd_sha256=manifest.fingerprint.digest if manifest.fingerprint else None,
        )
    )

    registry_entity = _uri(run_id, "entity", "registry-snapshot")
    nodes.append(
        ProvEntity(
            id=registry_entity,
            type="prov:Entity",
            label=f"registry snapshot ({manifest.registry_route})",
            dd_version=manifest.registry_snapshot.version,
        )
    )

    ranking_entity = _uri(run_id, "entity", "ranking-config")
    nodes.append(
        ProvEntity(
            id=ranking_entity,
            type="prov:Entity",
            label="ranking configuration",
            dd_version=manifest.ranking_config.version,
            dd_sha256=manifest.ranking_config.sha256,
        )
    )

    intake_entity: str | None = None
    if manifest.intake_config is not None:
        intake_entity = _uri(run_id, "entity", "intake-config")
        nodes.append(
            ProvEntity(
                id=intake_entity,
                type="prov:Entity",
                label="intake question set",
                dd_version=manifest.intake_config.version,
                dd_sha256=manifest.intake_config.sha256,
            )
        )

    prompt_entities: dict[str, str] = {}
    for prompt in manifest.prompts:
        entity_id = _uri(run_id, "entity", "prompt", prompt.name, prompt.version)
        prompt_entities[prompt.name] = entity_id
        nodes.append(
            ProvEntity(
                id=entity_id,
                type="prov:Entity",
                label=f"prompt {prompt.name}",
                dd_version=prompt.version,
                dd_sha256=prompt.sha256,
                dd_path=f"prompts/{prompt.name}.{prompt.version}.md",
            )
        )

    # -- one activity per stage ----------------------------------------------------------

    previous_activity: str | None = None
    stage_activities: dict[str, str] = {}
    for report in manifest.stages:
        activity_id = _uri(run_id, "activity", report.stage)
        stage_activities[report.stage] = activity_id

        used = [_primary_input(report.stage, input_entity, registry_entity, intake_entity)]
        if report.stage == StageName.RANK:
            used.append(ranking_entity)
        used.extend(prompt_entities[ref.name] for ref in report.prompts)

        agents = [software_agent]
        if report.model_id is not None:
            agents.append(model_agent)

        energy = None
        if report.model_id is not None:
            energy = EnergyEstimate(
                input_tokens=token_totals.get("input_tokens", 0),
                output_tokens=token_totals.get("output_tokens", 0),
                model_calls=manifest.model.calls,
            )

        nodes.append(
            ProvActivity(
                id=activity_id,
                type="prov:Activity",
                label=f"stage {report.stage}",
                started_at=report.started_at,
                ended_at=report.ended_at,
                used=used,
                associated_with=agents,
                informed_by=previous_activity,
                dd_status=report.status,
                dd_counts=report.counts or None,
                dd_energy=energy,
            )
        )
        previous_activity = activity_id

    # -- outputs -------------------------------------------------------------------------

    # The elicitation, as an entity in its own right. R10 requires the actions an agent takes on
    # metadata be auditable, and asking a researcher a set of questions and recording their
    # answers is one — the answers then steer every registry query the run makes, so a profile
    # that used them has to say so.
    answers_entity: str | None = None
    if _asked_questions(manifest):
        answers_entity = _uri(run_id, "entity", "answers")
        nodes.append(
            ProvEntity(
                id=answers_entity,
                type="prov:Entity",
                label="intake answers",
                generated_by=stage_activities[StageName.ELICIT],
                derived_from=[entity for entity in (intake_entity,) if entity],
                dd_path=RUN_FILES["answers"],
            )
        )

    if "profile" in stage_activities:
        nodes.append(
            ProvEntity(
                id=_uri(run_id, "entity", "profile"),
                type="prov:Entity",
                label="dataset profile",
                generated_by=stage_activities["profile"],
                derived_from=[input_entity, *([answers_entity] if answers_entity else [])],
                dd_path="profile.json",
            )
        )

    if "assemble" in stage_activities:
        nodes.append(
            ProvEntity(
                id=_uri(run_id, "entity", "recommendations"),
                type="prov:Entity",
                label="recommendations document",
                generated_by=stage_activities["assemble"],
                derived_from=[input_entity, registry_entity, ranking_entity],
                dd_path="recommendations.json",
            )
        )

    return ProvDocument(graph=nodes)


def _asked_questions(manifest: RunManifest) -> bool:
    """Whether `elicit` actually put questions to anyone on this run.

    Read off the stage's own counts rather than the run's phase, so the record reflects what
    happened rather than what the input asked for. A collected run's `elicit` reports `empty`
    with no questions, and inventing an answers entity for it would put a file in the graph that
    was never written.
    """
    for report in manifest.stages:
        if report.stage is StageName.ELICIT:
            return report.counts.get("questions", 0) > 0
    return False
