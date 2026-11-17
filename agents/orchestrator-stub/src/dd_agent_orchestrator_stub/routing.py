"""How the stub reads `routing.yaml` (`agent.py`): the rules that route a message to an agent,
the phrases that name a Blueprint entry point, how a message asks what to do next, and the inputs
each step sends.

A message routes by the first rule whose pattern matches it, or, when it starts `@<agent>`, by
that agent's rule, so that a person can name the agent they want.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dd_sdk.process_flow import Entry, entry

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
