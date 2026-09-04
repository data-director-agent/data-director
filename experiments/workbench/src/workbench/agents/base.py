"""The agent interface the conductor calls.

An agent decides an outcome, a payload and the evidence it rests on. It does not fill in
identifiers, timestamps or telemetry; the conductor does, so an agent cannot mislabel its own
run. `action_class` is what the policy gate matches against `actions_requiring_approval`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from opentelemetry.trace import Tracer

from workbench.contract.models import EvidenceItem, InvocationRequest, Outcome, Recommendations


@dataclass(frozen=True)
class AgentResult:
    outcome: Outcome
    payload: Recommendations | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class RunContext:
    tracer: Tracer


@runtime_checkable
class Agent(Protocol):
    agent_id: str
    version: str
    requirement_ids: tuple[str, ...]
    action_class: str

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult: ...
