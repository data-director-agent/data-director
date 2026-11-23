"""The record's gaps: one question for each value the librarian leaves null, and the researcher's
answers placed in them (docs/specs/drafting.md, invariants 5 and 6).

A gap is named by its path in the record's JSON form (`gap_property`), property names joined by
dots with a list entry's position in brackets, such as `titles[0].title`. Its question's
identifier is `q-` and the first 16 hexadecimal digits of the SHA-256 of the canonical JSON of
`{"property": path}`, so it is the same in every draft that leaves the same gap, and the answer
recorded to it finds it again. An answer is placed as given, and that gap is asked no more.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dd_sdk.contract.models import DocumentQuestion, DraftAnswer

QUESTION_ID_DIGITS = 16
# A qualifier that names a vocabulary, such as subjectScheme: an entry asked for in one is chosen
# from it, so a model suggests one only from the vocabulary's own fields (`categories.py`).
_SCHEME_KEY = re.compile(r"Scheme$")


@dataclass(frozen=True, slots=True)
class Gap:
    """One value left null: its path in the record, the property it belongs to in the rule
    table (`titles`, `types.resourceTypeGeneral`), and the qualifiers beside it in its entry."""

    path: str
    prop: str
    qualifier: Mapping[str, Any]

    @property
    def question_id(self) -> str:
        return question_id(self.path)

    @property
    def names_a_vocabulary(self) -> bool:
        return any(_SCHEME_KEY.search(key) for key in self.qualifier)

    @property
    def vocabulary(self) -> str | None:
        """The vocabulary the entry's qualifier names, such as `ANZSRC Fields of Research`."""
        named = [v for k, v in self.qualifier.items() if _SCHEME_KEY.search(k) and v]
        return str(named[0]) if named else None


def question_id(path: str) -> str:
    canonical = json.dumps({"property": path}, sort_keys=True, separators=(",", ":"))
    return "q-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:QUESTION_ID_DIGITS]


def gaps(record: Mapping[str, Any]) -> list[Gap]:
    """Every null value in `record`, in the order the record is written."""
    return list(_walk(record, "", ""))


def _walk(node: Any, path: str, prop: str) -> Iterator[Gap]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, list):
                for i, entry in enumerate(value):
                    yield from _entry(entry, f"{child}[{i}]", _join(prop, key))
            elif value is None:
                yield Gap(child, _join(prop, key), {})
            else:
                yield from _walk(value, child, _join(prop, key))


def _entry(entry: Any, path: str, prop: str) -> Iterator[Gap]:
    """The null values of one list entry: an entry is an object whose value key may be null,
    beside the qualifiers the repository asks for."""
    if entry is None:
        yield Gap(path, prop, {})
    elif isinstance(entry, Mapping):
        qualifier = {k: v for k, v in entry.items() if v is not None and isinstance(v, str)}
        for key, value in entry.items():
            if value is None:
                yield Gap(f"{path}.{key}", prop, qualifier)


def _join(prop: str, key: str) -> str:
    return f"{prop}.{key}" if prop else str(key)


def answers_by_question(answers: Sequence[DraftAnswer]) -> dict[str, str]:
    """The text of each answer by the question it answers, skipping blank ones; a later answer to
    a question replaces an earlier one."""
    return {a.answered_question: a.answer_text for a in answers if a.answer_text.strip()}


def place(record: dict[str, Any], found: Sequence[Gap], answers: Mapping[str, str]) -> list[Gap]:
    """Place each answer, as given, in its gap; returns the gaps still open."""
    still: list[Gap] = []
    for gap in found:
        answer = answers.get(gap.question_id)
        if answer is None:
            still.append(gap)
        else:
            _set(record, gap.path, answer)
    return still


_STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _set(record: dict[str, Any], path: str, value: str) -> None:
    steps: list[str | int] = [name if name else int(index) for name, index in _STEP.findall(path)]
    node: Any = record
    for step in steps[:-1]:
        node = node[step]
    node[steps[-1]] = value


def ask(gap: Gap, prompts: Mapping[str, str | None]) -> DocumentQuestion:
    """The question put to the researcher about `gap`: the rule table's prompt for its property,
    or one naming the property, with the qualifiers the repository asks for."""
    prompt = prompts.get(gap.prop) or f"What is the dataset's {gap.prop}?"
    if gap.qualifier:
        prompt += " (" + ", ".join(f"{k}: {v}" for k, v in gap.qualifier.items()) + ")"
    return DocumentQuestion(
        question_id=gap.question_id, question_prompt=prompt, gap_property=gap.path
    )
