"""Categories: entries a repository asks for from a named subject classification, such as ORDA's
categories from the ANZSRC Fields of Research (#703, docs/specs/drafting.md).

The fields a model may choose from are retrieved through the tool gateway before any model is
called (`subjects.list_terms`, served by `mcp-subjects`), so the choice is from a closed set: the
scheme's own fields. A code the model gives that the set does not hold is dropped
(`suggest.check_suggestions`). Each code kept is retrieved again on its own
(`subjects.get_term`), and the suggestion offered is that record's label, cited by that record:
each suggested term cites the vocabulary record it came from. A code the gateway does not return
is not offered.

With no tools grant, a scheme the server does not know or a call that fails, no category is
suggested and the statement says why. That is an outcome, not an error: the question is still
asked. Keywords from other vocabularies, through terminology services, wait for the spike that
chooses them, TODO(#956).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from dd_sdk.agent import RunContext
from dd_sdk.tools import ToolGatewayError, ToolOutcome, ToolRecord, ToolUse

SERVER = "subjects"
LIST_TERMS = "list_terms"
GET_TERM = "get_term"
USES = (ToolUse(SERVER, (LIST_TERMS, GET_TERM)),)

NOT_GRANTED = "it was granted no tool server for subject classifications"

type Choices = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Offered:
    """The fields of each scheme retrieved, as (code, label) pairs, by the name the repository
    gives the scheme; and why any scheme's fields could not be retrieved."""

    choices: Mapping[str, Choices] = field(default_factory=dict)
    missing: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Cited:
    """The label offered for each question a code was chosen for, the records that give them,
    and why any chosen code was not offered."""

    labels: Mapping[str, str] = field(default_factory=dict)
    records: tuple[ToolRecord, ...] = ()
    dropped: tuple[str, ...] = ()


def _call(ctx: RunContext, tool: str, arguments: dict[str, str]) -> tuple[ToolRecord | None, str]:
    """The one record a call returned, or why there is none."""
    assert ctx.tools is not None
    try:
        outcome: ToolOutcome = ctx.tools.call(SERVER, tool, arguments)
    except ToolGatewayError as error:
        return None, f"the gateway refused the call: {error}"
    if outcome.is_error or not outcome.records:
        return None, "the server returned no record"
    return outcome.records[0], ""


def offer(ctx: RunContext, schemes: Iterable[str]) -> Offered:
    """The fields of each scheme named, retrieved through the gateway."""
    named = list(dict.fromkeys(schemes))
    if ctx.tools is None:
        return Offered(missing=dict.fromkeys(named, NOT_GRANTED))
    choices: dict[str, Choices] = {}
    missing: dict[str, str] = {}
    for scheme in named:
        record, why = _call(ctx, LIST_TERMS, {"scheme": scheme})
        terms = record.content.get("terms") if record is not None else None
        pairs = tuple(
            (str(t["code"]), str(t["label"]))
            for t in terms or ()
            if isinstance(t, dict) and t.get("code") and t.get("label")
        )
        if pairs:
            choices[scheme] = pairs
        else:
            missing[scheme] = why or "the server listed no fields"
    return Offered(choices, missing)


def cite(ctx: RunContext, chosen: Mapping[str, tuple[str, str]]) -> Cited:
    """Each chosen code (scheme and code, by question identifier) retrieved on its own: its label
    to offer, and the record that cites it."""
    if ctx.tools is None or not chosen:
        return Cited()
    labels: dict[str, str] = {}
    records: list[ToolRecord] = []
    dropped: list[str] = []
    for question, (scheme, code) in chosen.items():
        record, why = _call(ctx, GET_TERM, {"scheme": scheme, "code": code})
        label = record.content.get("label") if record is not None else None
        if record is None or not isinstance(label, str) or not label:
            dropped.append(f"{question}: {code} could not be retrieved from {scheme} ({why})")
            continue
        labels[question] = label
        if record not in records:
            records.append(record)
    return Cited(labels, tuple(records), tuple(dropped))


def sentence(offered: Offered, cited: Cited) -> str:
    """What the outcome says about categories: from which schemes, and why any were not
    suggested. Empty when no category was asked about."""
    parts: list[str] = []
    if cited.labels:
        n = len(cited.labels)
        parts.append(
            f"{n} {'category' if n == 1 else 'categories'} suggested from "
            f"{', '.join(offered.choices)}, each citing its field's record."
        )
    for scheme, why in offered.missing.items():
        parts.append(f"No category is suggested from {scheme}: {why}.")
    return " ".join(parts)
