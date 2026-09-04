"""`run.json` — the machine-readable summary of one run.

Everything needed to say what happened and reproduce the conditions: the agent identity (C13),
the model and the parameters *actually sent*, which prompts and weights were in force, which
copy of the registry answered, and what each stage did.
"""

from __future__ import annotations

from pydantic import Field

from standards_advisor.models.common import (
    AgentRef,
    Frozen,
    IntakeConfigRef,
    PromptRef,
    RankingConfigRef,
    RegistrySnapshotRef,
    StageFailure,
    StageReport,
)
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.models.profile import ContentFingerprint


class ModelRecord(Frozen):
    """What was asked of a model, as sent.

    `params` is what actually went over the wire. Recording the requested parameters instead
    would make the record a statement of intent rather than of fact — and since no sampling
    parameters are sent at all by default, the difference is the whole value of the field.
    """

    model_id: str
    params: dict[str, str] = Field(default_factory=dict)
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class RunManifest(Frozen):
    run_id: str
    started_at: str
    ended_at: str | None = None
    tool_version: str
    agent: AgentRef

    inputs: DatasetInput
    fingerprint: ContentFingerprint | None = None

    model: ModelRecord
    prompts: list[PromptRef] = Field(default_factory=list)
    ranking_config: RankingConfigRef
    intake_config: IntakeConfigRef | None = None
    """Which intake question set was in force (§8).

    Recorded on every run, not only pre-collection ones: the set was loaded and governed what
    `elicit` would have asked, and "this version asked nothing at this phase" is a fact about
    the version. R10 wants the actions recorded, and not asking is one of them."""
    registry_snapshot: RegistrySnapshotRef
    registry_route: str

    stages: list[StageReport] = Field(default_factory=list)
    failures: list[StageFailure] = Field(default_factory=list)

    exit_status: str = "incomplete"
    """`complete`, `complete_with_failures`, or `incomplete` if the run never finished. A run
    that abstained on everything is still `complete` — §5.5 is explicit that a run which finds
    nothing is a good run, and the manifest must not imply otherwise."""
