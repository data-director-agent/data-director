"""Building the §6.3 PROV-O graph from a run manifest and its event log.

Built from `run.json` plus `events.jsonl` — never by reading the checkpoint database. The
provenance record must not depend on a dependency's storage format, which is the same reason
the run directory exists at all (see `run_dir`).
"""

from __future__ import annotations

from standards_advisor.models.provenance import (
    EnergyEstimate,
    ProvActivity,
    ProvAgent,
    ProvDocument,
    ProvEntity,
)
from standards_advisor.provenance.manifest import RunManifest


def _uri(run_id: str, *parts: str) -> str:
    return "urn:dd:r3:" + ":".join([run_id, *parts])


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

        used = [registry_entity if report.stage in {"retrieve", "rank"} else input_entity]
        if report.stage == "rank":
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

    if "profile" in stage_activities:
        nodes.append(
            ProvEntity(
                id=_uri(run_id, "entity", "profile"),
                type="prov:Entity",
                label="dataset profile",
                generated_by=stage_activities["profile"],
                derived_from=[input_entity],
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
