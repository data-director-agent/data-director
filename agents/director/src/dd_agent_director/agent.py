"""director.stub: a rule-based stand-in for the Data Director orchestrator (ADR-0012).

The Blueprint's Data Director is an orchestrator: one agent a person converses with, which hands
work to specialist agents. This package is the smallest agent that exercises that shape through
the workbench, so the conversation contract, the delegation grant, the shell's chat screen and the
linter's `delegation` rules have something real to run against before a model-backed
orchestrator exists.

It routes each message by the first matching rule in `routing.yaml`, delegates to that rule's
agent through `ctx.delegate` (never directly: the workbench runs the child as a governed
invocation and records it), and replies with a template sentence naming the agent and version
that answered. It reads only the current message; the history in `Message.history` is covered
by the input hash but not used for routing.

Grounding mode `delegation`: the reply cites the input and each child envelope it relays, and
the linter checks those citations against the delegations the conductor recorded (R1, D1-D3,
G4). This agent calls no model, so its telemetry carries none. A model-backed orchestrator takes
the same spec with `reply_derivation` `model` and a `chat` span, and needs no contract change.

The parent succeeds when it has delegated and relayed the child's outcome, whatever that outcome
was; the child's own status is on its envelope and on the parent's `delegations`.
TODO: decide whether the LLM orchestrator should mirror a failed child's status.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Reply,
    parse_input,
)
from dd_sdk.delegate import Delegated
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

HERE = Path(__file__).resolve().parent
ROUTING = HERE / "routing.yaml"
UISCHEMA = HERE / "uischema.json"

MENTION = re.compile(r"^@(?P<agent>[\w.-]+)\s+(?P<rest>.+)$", re.DOTALL)


@dataclass(frozen=True)
class Rule:
    name: str
    agent_id: str
    pattern: re.Pattern[str]
    input: dict[str, Any]
    mention_input: dict[str, Any]
    relay_field: str | None
    example: str


def load_rules(path: Path = ROUTING) -> list[Rule]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Rule(
            name=r["name"],
            agent_id=r["agent_id"],
            pattern=re.compile(r["pattern"], re.IGNORECASE | re.DOTALL),
            input=r["input"],
            mention_input=r["mention_input"],
            relay_field=r.get("relay_field"),
            example=r["example"],
        )
        for r in doc["rules"]
    ]


def fill(template: Any, values: dict[str, str]) -> Any:
    """Fill `{name}` placeholders in every string of a template document."""
    if isinstance(template, str):
        return template.format_map(values)
    if isinstance(template, dict):
        return {k: fill(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, values) for v in template]
    return template


@dataclass(frozen=True)
class Route:
    rule: Rule
    input_document: dict[str, Any]


def route(text: str, rules: list[Rule]) -> Route | str:
    """The rule a message routes by and the child input it builds, or why there is none."""
    text = text.strip()
    mention = MENTION.match(text)
    if mention:
        agent_id, rest = mention["agent"], mention["rest"].strip()
        for rule in rules:
            if rule.agent_id == agent_id:
                match = rule.pattern.match(rest)
                if match:
                    return Route(rule, fill(rule.input, match.groupdict()))
                return Route(rule, fill(rule.mention_input, {"rest": rest}))
        return f"No routing rule names {agent_id!r}."
    for rule in rules:
        match = rule.pattern.match(text)
        if match:
            return Route(rule, fill(rule.input, match.groupdict()))
    return "No routing rule matched the message."


class DirectorStub:
    spec = AgentSpec(
        agent_id="director.stub",
        version="0.1.0",
        description=(
            "A rule-based stand-in for the Data Director orchestrator. Routes each message to "
            "one specialist agent through the workbench and relays its answer."
        ),
        requirement_ids=(
            "DD-CONVERSATION",
            "DD-DELEGATION",
            "DD-GROUNDING-MODE",
            "DD-GROUNDED-PAYLOAD",
        ),
        action_class="advise",
        accepts=(Message,),
        grounding_mode=GroundingMode.DELEGATION,
        payload_type=Reply,
        uischema=json.loads(UISCHEMA.read_text(encoding="utf-8")),
    )

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else load_rules()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        message = request.input
        assert isinstance(message, Message)  # the conductor refused anything else

        if ctx.delegate is None:
            return _abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                "The workbench gave this run no way to delegate (for example, it was started "
                "from `workbench invoke`), so no agent was asked.",
            )
        found = route(message.message_text, self.rules)
        if isinstance(found, str):
            return _abstain(ReasonCode.OUTSIDE_AGENT_SCOPE, f"{found} {self._routable()}")

        # A refused delegation (unknown agent, unreachable workbench) raises DelegationRefused;
        # the conductor records it as failed(agent-error), which is what a developer should see.
        delegated = ctx.delegate(found.rule.agent_id, parse_input(found.input_document))
        return self._relay(found.rule, delegated, ctx)

    def _relay(self, rule: Rule, delegated: Delegated, ctx: RunContext) -> AgentResult:
        child = delegated.envelope
        text = (
            f"Routed to {child.agent_id}@{child.agent_version} by rule {rule.name!r}. "
            f"It {child.outcome.status.value}: {child.outcome.statement}"
        )
        if child.payload is not None and rule.relay_field:
            value = getattr(child.payload, rule.relay_field, None)
            if value:
                text += f" {rule.relay_field}: {value}"
        input_ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Delegated to {child.agent_id}@{child.agent_version}; its outcome is on the "
                    "delegated envelope. Rule-based; human review is required."
                ),
            ),
            payload=Reply(
                reply_text=text,
                reply_derivation=Derivation.TEMPLATE,
                grounded_on=[input_ref, delegated.ref],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                ),
                delegated.evidence,
            ],
        )

    def _routable(self) -> str:
        examples = "; ".join(f"{r.example!r} → {r.agent_id}" for r in self.rules)
        return f"Try: {examples}; or '@<agent_id> <text>'."


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def build() -> DirectorStub:
    return DirectorStub()


def main() -> int:
    """The `dd-director` console script: serve this agent over A2A with `dd_sdk.serve`."""
    return serve.main(build)
