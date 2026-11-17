"""What an agent's `run` returns (`dd_sdk.agent`): an outcome, a payload and the evidence it rests
on, with the model calls it made. The conductor builds the envelope from it.

It lives apart from `dd_sdk.agent` so that `dd_sdk.wire`, which carries it across A2A, need not
import the agent interface; `dd_sdk.agent` re-exports it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from dd_sdk.contract.models import EvidenceItem, Grounded, ModelCall, Outcome


@dataclass(frozen=True)
class AgentResult:
    outcome: Outcome
    payload: Grounded | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Each model call, and the prompts they name by digest (`dd_sdk.prompts`,
    # docs/specs/disclosure.md). The conductor puts the calls in the envelope's telemetry and keeps
    # the prompts beside the run, never in the envelope.
    model_calls: tuple[ModelCall, ...] = ()
    prompts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
