"""Matchers: what the rules leave over, read by a model (docs/specs/agents.md, Model-backed
personas).

The rules in `agent.py` match outputs by exact name, case ignored, and compare repository, access
and licence as text. What they leave over is the `Residue`: committed outputs with no planned
output of the same name, planned outputs with no committed one, and the aspects of matched outputs
whose text differs. A matcher is given only the residue, never the outputs the rules matched
exactly, and proposes:

- pairings: a committed output that is planned under another name ("Interview transcripts" is now
  "Anonymised interview transcripts"), each with a short reason; and
- equivalences: two names for one repository, access level or licence ("CC-BY" and
  "CC-BY-4.0"), each with a short reason.

`ModelMatcher` is the default (`DD_DMP_MATCHER` unset or `model`, `factory.py`); `TemplateMatcher`
(`DD_DMP_MATCHER=template`) proposes nothing, so the rules' result stands, and needs no key.
`ModelMatcher` calls whichever model the agent's settings name through the SDK's model seam
(`dd_sdk.model`, `dd_sdk.model_provider`), so this package imports no model provider's SDK. The
model replies against a schema (`MatchReply`), which the provider constrains it to.

What the model proposes is checked before it is used (`check`). A pairing must name a committed
output the rules left missing and a planned output they left unplanned, each once; an equivalence
must name an aspect and two values found on the two sides of the input. Anything else is dropped
and recorded. A refused reply, a reply that is not the schema's JSON, or a model that cannot be
reached leaves the rules' result as it is, and the agent says so. A proposal never removes a flag
from review: a pairing merges two flags into one, and an equivalence moves a flag to the payload's
`reconciled` list, both shown to the person reviewing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_agent_advisor_dmp.classes import SharingCommitment
from dd_sdk.agent import RunContext
from dd_sdk.model import CallOptions, Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may propose; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
# The aspects of a commitment compared when an output is both committed and planned, in order.
COMPARED = ("repository", "access", "licence")
# The longest reason kept, in characters: a short reason, not an essay.
MAX_REASON = 300


def key(text: str) -> str:
    """How names and values are compared by rule: case and surrounding spaces ignored."""
    return text.strip().casefold()


@dataclass(frozen=True)
class Difference:
    """An aspect of an output on both lists whose text differs."""

    output: str
    aspect: str
    committed: str
    planned: str


@dataclass(frozen=True)
class Residue:
    """What the rules leave over: all a matcher is given."""

    missing: tuple[SharingCommitment, ...] = ()
    unplanned: tuple[SharingCommitment, ...] = ()
    differences: tuple[Difference, ...] = ()

    @property
    def readable(self) -> bool:
        """Whether there is anything a matcher could propose: a pairing needs an output on each
        side, an equivalence a difference."""
        return bool(self.missing and self.unplanned) or bool(self.differences)


class _Reply(BaseModel):
    # A reply with a key the schema does not name does not match it.
    model_config = ConfigDict(extra="forbid")


class ProposedPairing(_Reply):
    """A committed output that is planned under another name."""

    committed: str
    planned: str
    reason: str | None


class ProposedEquivalence(_Reply):
    """Two values of one aspect that name the same thing."""

    aspect: str
    committed: str
    planned: str
    reason: str | None


class MatchReply(_Reply):
    """What the model replies with. Every field is required, as a provider's strict schema
    needs; an empty list proposes nothing."""

    pairings: list[ProposedPairing]
    equivalences: list[ProposedEquivalence]


@dataclass(frozen=True)
class Pairing:
    """A kept pairing: the committed and planned outputs, as the input names them."""

    committed: SharingCommitment
    planned: SharingCommitment
    reason: str


@dataclass(frozen=True)
class Equivalence:
    """A kept equivalence, compared as the rules compare text."""

    aspect: str
    committed: str
    planned: str
    reason: str


@dataclass(frozen=True)
class Matches:
    """What a matcher proposed and the checks kept. Returned rather than kept on the matcher,
    because one matcher serves concurrent runs."""

    pairings: tuple[Pairing, ...] = ()
    equivalences: tuple[Equivalence, ...] = ()
    # The proposals that were not used, and why, for the payload and the outcome's statement.
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used (a refusal, a reply that is not JSON), if so.
    unused: str | None = None
    # The model configured, whether or not it was called; None on the template path.
    model_id: str | None = None
    # Whether the model was called: not when the rules leave nothing for it to read.
    called: bool = False
    usage: Usage = field(default_factory=Usage)
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None

    def equivalent(self, aspect: str, committed: str, planned: str) -> Equivalence | None:
        """The kept equivalence for these two values of `aspect`, if there is one."""
        for e in self.equivalences:
            if (e.aspect, key(e.committed), key(e.planned)) == (
                aspect,
                key(committed),
                key(planned),
            ):
                return e
        return None


class Matcher(Protocol):
    model_id: str | None

    def match(self, residue: Residue, ctx: RunContext) -> Matches: ...


class TemplateMatcher:
    """Proposes nothing: the rules' result stands."""

    model_id: str | None = None

    def match(self, residue: Residue, ctx: RunContext) -> Matches:
        return Matches()


class ModelMatcher:
    """Proposes pairings and equivalences with the model the agent's settings name
    (`dd_sdk.model_provider`), or a `dd_sdk.testing.FakeModel` in tests. Emits one `chat` span per
    call, carrying the model id and the token counts (`dd_sdk.model.call`)."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def match(self, residue: Residue, ctx: RunContext) -> Matches:
        if not residue.readable:
            return Matches(model_id=self.model_id)
        log = ModelCallLog(self.model.provider)
        messages = [{"role": "user", "content": prompt(residue)}]
        try:
            reply = call(
                self.model,
                ctx,
                system=SYSTEM_PROMPT,
                messages=messages,
                schema=MatchReply,
                options=CallOptions(calls=log),
            )
        except ModelCallError as error:
            return self._unused(f"the model could not be reached ({error})", log)
        except ModelOutputError as error:
            # An endpoint that does not constrain its output may fence the JSON, or stray from
            # the schema; a fenced reply that matches is used, anything else is not.
            got = error.reply
            try:
                parsed = MatchReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                return self._unused(
                    "the model's reply did not match its schema", got.calls, got.usage, got.model_id
                )
            return check(parsed, residue, got.model_id, got.usage, got.calls)
        if reply.parsed is None:
            return self._unused("the model declined", reply.calls, reply.usage, reply.model_id)
        return check(reply.parsed, residue, reply.model_id, reply.usage, reply.calls)

    def _unused(
        self,
        why: str,
        calls: ModelCallLog,
        usage: Usage | None = None,
        model_id: str | None = None,
    ) -> Matches:
        return Matches(
            unused=why,
            model_id=model_id or self.model_id,
            called=True,
            usage=usage or Usage(),
            calls=calls,
        )


def prompt(residue: Residue) -> str:
    """The user message: the residue, as JSON. Nothing the rules matched exactly is sent."""

    def commitment(c: SharingCommitment) -> dict[str, Any]:
        return c.model_dump(include={"output", *COMPARED}, exclude_none=True)

    return "What the rules left over, as JSON:\n" + json.dumps(
        {
            "committed_not_planned": [commitment(c) for c in residue.missing],
            "planned_not_committed": [commitment(p) for p in residue.unplanned],
            "differences": [
                {
                    "output": d.output,
                    "aspect": d.aspect,
                    "committed": d.committed,
                    "planned": d.planned,
                }
                for d in residue.differences
            ],
        },
        ensure_ascii=False,
        indent=1,
    )


def check(
    reply: MatchReply,
    residue: Residue,
    model_id: str | None = None,
    usage: Usage | None = None,
    calls: ModelCallLog | None = None,
) -> Matches:
    """The proposals of a model's reply that may be used, and why any others were not."""
    missing = {key(c.output): c for c in residue.missing}
    unplanned = {key(p.output): p for p in residue.unplanned}
    dropped: list[str] = []
    pairings: list[Pairing] = []
    paired_committed: set[str] = set()
    paired_planned: set[str] = set()
    for p in reply.pairings:
        label = f"pairing '{p.committed}' with '{p.planned}'"
        c_key, p_key = key(p.committed), key(p.planned)
        why = (
            f"names '{p.committed}', which is not a committed output left unmatched"
            if c_key not in missing
            else f"names '{p.planned}', which is not a planned output left unmatched"
            if p_key not in unplanned
            else "paired twice"
            if c_key in paired_committed or p_key in paired_planned
            else _no_reason(p.reason)
        )
        if why:
            dropped.append(f"{label}: {why}")
            continue
        paired_committed.add(c_key)
        paired_planned.add(p_key)
        pairings.append(Pairing(missing[c_key], unplanned[p_key], _tidy(p.reason)))

    # The values an equivalence may name: those on each side of the input, for each aspect, from
    # the differences and from the outputs left unmatched, whose aspects a pairing compares.
    sides: dict[str, tuple[set[str], set[str]]] = {a: (set(), set()) for a in COMPARED}
    for d in residue.differences:
        sides[d.aspect][0].add(key(d.committed))
        sides[d.aspect][1].add(key(d.planned))
    for aspect in COMPARED:
        sides[aspect][0].update(key(v) for c in residue.missing if (v := getattr(c, aspect)))
        sides[aspect][1].update(key(v) for p in residue.unplanned if (v := getattr(p, aspect)))
    equivalences: list[Equivalence] = []
    seen: set[tuple[str, str, str]] = set()
    for e in reply.equivalences:
        label = f"{e.aspect} '{e.committed}' as '{e.planned}'"
        triple = (e.aspect, key(e.committed), key(e.planned))
        why = (
            f"'{e.aspect}' is not an aspect it may reconcile"
            if e.aspect not in sides
            else f"names '{e.committed}', which is not a committed {e.aspect} in the input"
            if triple[1] not in sides[e.aspect][0]
            else f"names '{e.planned}', which is not a planned {e.aspect} in the input"
            if triple[2] not in sides[e.aspect][1]
            else "proposed twice"
            if triple in seen
            else _no_reason(e.reason)
        )
        if why:
            dropped.append(f"{label}: {why}")
            continue
        seen.add(triple)
        equivalences.append(Equivalence(e.aspect, e.committed, e.planned, _tidy(e.reason)))

    return Matches(
        pairings=tuple(pairings),
        equivalences=tuple(equivalences),
        dropped=tuple(dropped),
        model_id=model_id,
        called=True,
        usage=usage or Usage(),
        calls=calls,
    )


def _no_reason(reason: str | None) -> str | None:
    """Why a proposal's reason cannot be used, or None if it can."""
    if reason is None or not reason.strip():
        return "gives no reason"
    if len(reason) > MAX_REASON:
        return "its reason is too long"
    return None


def _tidy(reason: str | None) -> str:
    return " ".join((reason or "").split())


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped


def residue_of(
    committed: Sequence[SharingCommitment], planned: Sequence[SharingCommitment]
) -> Residue:
    """What the rules leave over from these two lists."""
    planned_by_name = {key(p.output): p for p in planned}
    committed_names = {key(c.output) for c in committed}
    missing, differences = [], []
    for c in committed:
        p = planned_by_name.get(key(c.output))
        if p is None:
            missing.append(c)
            continue
        differences.extend(differences_between(c, p))
    unplanned = [p for p in planned if key(p.output) not in committed_names]
    return Residue(tuple(missing), tuple(unplanned), tuple(differences))


def differences_between(c: SharingCommitment, p: SharingCommitment) -> list[Difference]:
    """The aspects whose text differs, where both sides give them, named by the committed output."""
    found = []
    for aspect in COMPARED:
        was, now = getattr(c, aspect), getattr(p, aspect)
        if was is not None and now is not None and key(was) != key(now):
            found.append(Difference(c.output, aspect, was, now))
    return found


def model_use(model_id: str | None, usage: Usage, calls: ModelCallLog | None) -> dict[str, Any]:
    """What a result records of the model calls a matcher or reader made."""
    return {
        "model_id": model_id,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "model_calls": tuple(calls.calls) if calls is not None else (),
        "prompts": dict(calls.prompts) if calls is not None else {},
    }
