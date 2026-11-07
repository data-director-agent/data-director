"""orchestrator.stub: a rule-based stand-in for the Data Director orchestrator
(docs/specs/orchestration.md).

The Blueprint's Data Director is an orchestrator: one agent a person converses with, which hands
work to specialist agents. This package is the smallest agent that exercises that shape through
the harness, so the conversation contract, the delegation grant, the viewer's chat screen and the
linter's `delegation` rules have something real to run against before a model-backed
orchestrator exists. `orchestrator.model` (`agents/orchestrator-model/`) is that orchestrator;
this one stays as the model-free reference, and the app's default.

It routes each message by the first matching rule in `routing.yaml`, delegates to that rule's
agent through `ctx.delegate` (never directly: the conductor runs the child as a governed
invocation and records it), and replies with a template sentence naming the agent and version
that answered.

A message no rule matches may name one of the Blueprint's three entry points (§8.1): before data
collection, data collected and being prepared for sharing, or ready to deposit. The reply then lists
every step from that entry's phase to the last, with the agents whose manifest entry serves the
step, and says "no agent yet" with the step's requirement where none does
(docs/specs/orchestration.md). On a first turn that names neither a rule nor an entry, it asks which
entry applies, as a choice question (`Reply.reply_question`) whose values are the entry numbers; a
`Message.choice_answer` naming one is read before any rule. Otherwise it reads only the current
message: `Message.history` is covered by the input hash, and used only to tell a first turn.

In a project, the conductor says which entry point the researcher chose and how far each step has
gone (`Message.project_entry`, `Message.project_progress`), derived from the project log on every
turn. The stub keeps no place of its own: its list of steps marks each one done, started or
skipped, and ends with the step `suggested_next` names. Asked what to do next ("what next?"), or on
a first turn in a project whose entry point is known, it offers that step and a few other open
ones as a choice question whose values are step ids. Choosing a step delegates the inputs
`routing.yaml` gives for it to the agent serving it, which the conductor fills from the project;
a step with agents but no template is answered with how to ask them, and a step with no agent is
named as having none. Nothing is a gate: any step may be chosen, and any rule still routes
(docs/specs/orchestration.md).

Grounding mode `delegation`: the reply cites the input and each child envelope it relays, and
the linter checks those citations against the delegations the conductor recorded (R1, D1-D3,
G4). This agent calls no model, so its telemetry carries none.

The parent succeeds when it has delegated and relayed the child's outcome, whatever that outcome
was; the child's own status is on its envelope and on the parent's `delegations`
(docs/specs/orchestration.md decision 14).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    ChoiceOption,
    ChoiceQuestion,
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Message,
    OpenInput,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Reply,
)
from dd_sdk.delegate import Delegated
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION
from dd_sdk.process_flow import (
    ENTRIES,
    PHASES,
    Entry,
    ProgressStep,
    Step,
    entry,
    progress,
    suggested_next,
)

HERE = Path(__file__).resolve().parent
ROUTING = HERE / "routing.yaml"

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


@dataclass(frozen=True)
class EntryRule:
    entry: Entry
    pattern: re.Pattern[str]


def load_entries(path: Path = ROUTING) -> list[EntryRule]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        EntryRule(entry(int(e["entry"])), re.compile(e["pattern"], re.IGNORECASE | re.DOTALL))
        for e in doc.get("entries") or []
    ]


def load_next(path: Path = ROUTING) -> re.Pattern[str] | None:
    """How a message asks what to do next, if `routing.yaml` says."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    pattern = doc.get("next")
    return re.compile(pattern, re.IGNORECASE) if pattern else None


def load_steps(path: Path = ROUTING) -> dict[str, list[dict[str, Any]]]:
    """The inputs to send when a step is chosen, by step id."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(k): list(v) for k, v in (doc.get("steps") or {}).items()}


def entry_named(text: str, entries: list[EntryRule]) -> Entry | None:
    """The entry point a message names, if any."""
    text = text.strip()
    return next((e.entry for e in entries if e.pattern.search(text)), None)


def entry_question() -> ChoiceQuestion:
    """Which entry point applies, as a choice question whose values are the entry numbers."""
    return ChoiceQuestion(
        question_prompt="Where are you with your research data?",
        question_options=[
            ChoiceOption(
                option_value=str(e.number), option_label=f"{e.text[0].upper()}{e.text[1:]}"
            )
            for e in ENTRIES
        ],
    )


def entry_chosen(message: Message) -> Entry | None:
    """The entry point the researcher chose in answer to `entry_question`, if they chose one."""
    answer = message.choice_answer
    if answer is None or len(answer.answer_values) != 1:
        return None
    try:
        return entry(int(answer.answer_values[0]))
    except KeyError, ValueError:
        return None


STEP_IDS = {s.id for p in PHASES for s in p.steps}
# How many open steps a "what next?" question offers besides the suggested one.
OTHER_STEPS = 3


def step_chosen(message: Message) -> str | None:
    """The step the researcher chose in answer to `next_question`, if they chose one."""
    answer = message.choice_answer
    if answer is None or len(answer.answer_values) != 1:
        return None
    value = answer.answer_values[0]
    return value if value in STEP_IDS else None


def project_entry(message: Message) -> Entry | None:
    """The entry point the conductor says the project's researcher chose, if any."""
    return entry(message.project_entry) if message.project_entry is not None else None


def states_of(message: Message) -> dict[str, str]:
    """Each step's state as the conductor derived it from the project log; open if left out."""
    return {p.step_id: p.step_state.value for p in message.project_progress or []}


def next_question(steps: list[ProgressStep], start: Entry | None) -> ChoiceQuestion | None:
    """The suggested step and up to `OTHER_STEPS` other open or started ones, as a choice whose
    values are step ids; None when fewer than two are left to offer."""
    first = suggested_next(steps, start)
    offered = [first] if first is not None else []
    for s in steps:
        if len(offered) > OTHER_STEPS:
            break
        if (
            s not in offered
            and s.state in ("open", "started")
            and not s.step.out_of_scope
            and (start is None or s.phase.number >= start.starts_at)
        ):
            offered.append(s)
    if len(offered) < 2:
        return None
    return ChoiceQuestion(
        question_prompt="What would you like to do next?",
        question_options=[
            ChoiceOption(
                option_value=s.step.id,
                option_label=s.step.label or s.step.text,
                option_help=("Suggested next. " if s is first else "")
                + f"Phase {s.phase.number}, {s.phase.name or s.phase.title}.",
            )
            for s in offered
        ],
        question_other=True,
    )


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
        agent_id="orchestrator.stub",
        title="Data Director",
        version="0.1.0",
        description=(
            "A rule-based stand-in for the Data Director orchestrator. Routes each message to "
            "one specialist agent through the conductor and relays its answer, or asks where "
            "the researcher is and lists the steps from that Blueprint entry point."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.DELEGATION,
        payload=ClassSchema.of(Reply),
        derivations={
            "reply_text": Derived(Derivation.TEMPLATE, recorded_in="reply_derivation"),
            "reply_question": Derived(Derivation.TEMPLATE),
        },
    )

    def __init__(
        self,
        rules: list[Rule] | None = None,
        entries: list[EntryRule] | None = None,
        next_pattern: re.Pattern[str] | None = None,
        steps: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.rules = rules if rules is not None else load_rules()
        self.entries = entries if entries is not None else load_entries()
        self.next_pattern = next_pattern if next_pattern is not None else load_next()
        self.steps = steps if steps is not None else load_steps()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        message = request.input
        assert isinstance(message, Message)  # the conductor refused anything else

        if ctx.delegate is None:
            return _abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                "The conductor gave this run no way to delegate (for example, it was started "
                "from `workbench invoke`), so no agent was asked.",
            )
        step_id = step_chosen(message)
        if step_id is not None:
            return self._do_step(step_id, message, ctx)
        chosen = entry_chosen(message)
        if chosen is not None:
            return self._where(
                chosen,
                message,
                ctx,
                f"Listed the steps from entry point {chosen.number}, as chosen; "
                "no agent was asked.",
            )
        found = route(message.message_text, self.rules)
        if isinstance(found, str):
            start = entry_named(message.message_text, self.entries)
            if start is not None:
                return self._where(
                    start,
                    message,
                    ctx,
                    f"Listed the steps from entry point {start.number}; no agent was asked.",
                )
            known = project_entry(message)
            asks_next = bool(self.next_pattern and self.next_pattern.search(message.message_text))
            if asks_next or (known is not None and not message.history):
                return self._where(
                    known,
                    message,
                    ctx,
                    "Listed where the project is and suggested a next step; no agent was asked.",
                )
            if not message.history:
                return _template_reply(
                    f"Where are you with your research data? Choose one below, or ask for one "
                    f"thing directly. {self._routable()}",
                    "Asked which entry point applies; no agent was asked.",
                    ctx,
                    question=entry_question(),
                )
            return _abstain(ReasonCode.OUTSIDE_AGENT_SCOPE, f"{found} {self._routable()}")

        # A refused delegation (unknown agent, unreachable conductor) raises DelegationRefused;
        # the conductor records it as failed(agent-error), which is what a developer should see.
        delegated = ctx.delegate(
            found.rule.agent_id, OpenInput.model_validate(found.input_document)
        )
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
            evidence=[_input_evidence(ctx), delegated.evidence],
        )

    def _where(
        self, start: Entry | None, message: Message, ctx: RunContext, statement: str
    ) -> AgentResult:
        """The steps from `start` with how far each has gone, and the suggested next step offered
        with a few others as a choice."""
        assert ctx.delegate is not None
        manifest = ctx.delegate.manifest()
        steps = progress(start, states_of(message), manifest)
        return _template_reply(
            self._plan_text(start, steps, manifest),
            statement,
            ctx,
            question=next_question(steps, start),
        )

    def _names(self, manifest: list[dict[str, Any]]) -> dict[str, str]:
        # The persona's title where its card gives one (docs/specs/agents.md), with the id to
        # @-mention it by.
        return {
            str(e.get("agent_id")): f"{e['title']} ({e.get('agent_id')})"
            if e.get("title")
            else str(e.get("agent_id"))
            for e in manifest
        }

    def _plan_text(
        self, start: Entry | None, steps: list[ProgressStep], manifest: list[dict[str, Any]]
    ) -> str:
        examples = {r.agent_id: r.example for r in self.rules}
        names = self._names(manifest)
        if start is not None:
            lines = [f"Entry point {start.number}: {start.text}. The steps from here:"]
        else:
            lines = ["Every step of the journey:"]
        phase = None
        for planned in steps:
            if planned.phase is not phase:
                phase = planned.phase
                lines.append(f"Phase {phase.number}, {phase.title}:")
            step = planned.step
            label = step.text + (" (optional)" if step.optional else "")
            requirements = ", ".join(step.requirements) or "no Blueprint requirement"
            state = {"done": "[done] ", "started": "[started] ", "skipped": "[skipped] "}.get(
                planned.state, ""
            )
            if step.out_of_scope:
                lines.append(f"- {state}{label}: out of scope for now.")
            elif planned.agent_ids:
                asks = "; ".join(
                    f"{names.get(a, a)}, for example {examples[a]!r}"
                    if a in examples
                    else names.get(a, a)
                    for a in planned.agent_ids
                )
                lines.append(f"- {state}{label} ({requirements}): {asks}.")
            else:
                lines.append(f"- {state}{label}: no agent yet ({requirements}).")
        suggested = suggested_next(steps, start)
        if suggested is not None:
            lines.append(
                f"Suggested next: {suggested.step.text}. You may do any step in any order, and "
                "mark one done or skipped in your project when nothing here records it."
            )
        elif any(s.state != "open" for s in steps):
            lines.append("Every step from here is done or skipped.")
        lines.append("The work and every decision are yours; the agents only advise.")
        return "\n".join(lines)

    def _do_step(self, step_id: str, message: Message, ctx: RunContext) -> AgentResult:
        """Delegate the inputs `routing.yaml` gives for the chosen step to the agents serving it,
        or say why none can be asked."""
        assert ctx.delegate is not None
        manifest = ctx.delegate.manifest()
        planned = next(
            p for p in progress(None, states_of(message), manifest) if p.step.id == step_id
        )
        step = planned.step
        requirements = ", ".join(step.requirements) or "no Blueprint requirement"
        if step.out_of_scope:
            return _template_reply(
                f"{step.text}: out of scope for now.",
                f"Chosen step {step_id} is out of scope; no agent was asked.",
                ctx,
            )
        if not planned.agent_ids:
            return _template_reply(
                f"{step.text}: no agent yet ({requirements}). The work is yours; mark the step "
                "done or skipped in your project when it is.",
                f"Chosen step {step_id} has no agent; no agent was asked.",
                ctx,
            )
        accepts = {
            str(e.get("agent_id")): {str(c) for c in e.get("accepts") or []} for e in manifest
        }
        sends = [
            (agent_id, template)
            for template in self.steps.get(step_id, [])
            for agent_id in [
                next(
                    (
                        a
                        for a in planned.agent_ids
                        if template["schema_class"] in accepts.get(a, ())
                    ),
                    None,
                )
            ]
            if agent_id is not None
        ]
        if not sends:
            names = self._names(manifest)
            who = "; ".join(names.get(a, a) for a in planned.agent_ids)
            return _template_reply(
                f"{step.text} ({requirements}): ask {who} directly, with "
                f"'@{planned.agent_ids[0]} <what you need>'.",
                f"Chosen step {step_id} needs the researcher's words; no agent was asked.",
                ctx,
            )
        delegated = [
            ctx.delegate(agent_id, OpenInput.model_validate(template))
            for agent_id, template in sends
        ]
        return self._relay_step(step, delegated, ctx)

    def _relay_step(self, step: Step, delegated: list[Delegated], ctx: RunContext) -> AgentResult:
        lines = [f"{step.text}:"]
        for d in delegated:
            child = d.envelope
            lines.append(
                f"- {child.agent_id}@{child.agent_version} {child.outcome.status.value}: "
                f"{child.outcome.statement}"
            )
        lines.append("Ask 'what next?' when you are ready.")
        input_ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        agents = ", ".join(f"{d.envelope.agent_id}@{d.envelope.agent_version}" for d in delegated)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Delegated step {step.id} to {agents}; each outcome is on its delegated "
                    "envelope. Rule-based; human review is required."
                ),
            ),
            payload=Reply(
                reply_text="\n".join(lines),
                reply_derivation=Derivation.TEMPLATE,
                grounded_on=[input_ref, *(d.ref for d in delegated)],
            ),
            evidence=[_input_evidence(ctx), *(d.evidence for d in delegated)],
        )

    def _routable(self) -> str:
        examples = "; ".join(f"{r.example!r} → {r.agent_id}" for r in self.rules)
        return f"Try: {examples}; or '@<agent_id> <text>'."


def _template_reply(
    text: str, statement: str, ctx: RunContext, question: ChoiceQuestion | None = None
) -> AgentResult:
    """A reply this agent writes itself, resting on the input alone."""
    return AgentResult(
        outcome=Outcome(
            status=OutcomeStatus.SUCCEEDED,
            statement=f"{statement} Rule-based; human review is required.",
        ),
        payload=Reply(
            reply_text=text,
            reply_derivation=Derivation.TEMPLATE,
            reply_question=question,
            grounded_on=[GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)],
        ),
        evidence=[_input_evidence(ctx)],
    )


def _input_evidence(ctx: RunContext) -> EvidenceItem:
    return EvidenceItem(
        source_id=ctx.input_ref,
        retrieved_at=datetime.now(UTC),
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=INPUT_CANONICALISATION,
        content_hash=ctx.input_hash,
    )


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def build() -> DirectorStub:
    return DirectorStub()


def main() -> int:
    """The `dd-orchestrator-stub` console script: serve this agent over A2A with `dd_sdk.serve`."""
    return serve.main(build)
