"""A long list asked of a model in batches, and what can be kept of a reply that does not parse.

A model asked for a suggestion for each of many questions replies with one list. Asked all at
once, the reply can run past the length the model may write and be cut off part-way, and a reply
that does not parse as a whole would lose every suggestion in it (#1318). So the questions are
asked in batches of at most `BATCH` (`batches`), each a call of its own, and when a reply does not
parse, the items of its list that are complete and match their schema are kept (`salvage`): a
reply cut off after its tenth item still gives nine or ten, and one malformed item costs only
itself.

Nothing here knows what the items are: the caller names the list's key and the item's schema, and
checks what is kept as it would check a reply that parsed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

# The most questions asked in one call. A dictionary suggestion is at most 200 characters, so a
# batch's reply stays well inside the default limit on what a model may write (4,096 tokens).
BATCH = 30

# Why a reply, or part of it, was not used, in words a researcher can follow.
CUT_SHORT = "the model's reply was too long and was cut off before it finished"
NOT_IN_FORM = "the model's reply was not in the form it was asked for"
ITEM_NOT_IN_FORM = "not in the form it was asked for"


def batches[T](items: Sequence[T], size: int = BATCH) -> list[Sequence[T]]:
    """`items` in order, in runs of at most `size`."""
    if size < 1:
        raise ValueError("a batch holds at least one item")
    return [items[i : i + size] for i in range(0, len(items), size)]


@dataclass(frozen=True)
class Salvaged[T: BaseModel]:
    """The items of a reply's list that could be kept, and an identifier for each that could not
    (its `id_key` if it gave one as a string, else None)."""

    items: tuple[T, ...] = ()
    unusable: tuple[str | None, ...] = ()


def salvage[T: BaseModel](text: str, key: str, item: type[T], id_key: str) -> Salvaged[T]:
    """The complete, well-formed items of the list under `key` in `text`, a JSON object that may
    be cut off or hold an item that does not match `item`. Reading stops at the first item that
    is not complete JSON, which is where a cut-off reply ends."""
    start = _list_start(text, key)
    if start is None:
        return Salvaged()
    decoder = json.JSONDecoder()
    kept: list[T] = []
    unusable: list[str | None] = []
    at = start
    while True:
        at = _skip(text, at, " \t\r\n,")
        if at >= len(text) or text[at] == "]":
            break
        try:
            value, at = decoder.raw_decode(text, at)
        except json.JSONDecodeError:
            break
        try:
            kept.append(item.model_validate(value))
        except ValidationError:
            given = value.get(id_key) if isinstance(value, dict) else None
            unusable.append(given if isinstance(given, str) else None)
    return Salvaged(tuple(kept), tuple(unusable))


def _list_start(text: str, key: str) -> int | None:
    """Where the items of the list under `key` begin, just after its `[`, or None."""
    marker = text.find(json.dumps(key))
    if marker < 0:
        return None
    at = _skip(text, marker + len(json.dumps(key)), " \t\r\n")
    if at >= len(text) or text[at] != ":":
        return None
    at = _skip(text, at + 1, " \t\r\n")
    if at >= len(text) or text[at] != "[":
        return None
    return at + 1


def _skip(text: str, at: int, chars: str) -> int:
    while at < len(text) and text[at] in chars:
        at += 1
    return at


def unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
