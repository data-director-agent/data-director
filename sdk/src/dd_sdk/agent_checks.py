"""The checks an `AgentSpec` makes of itself: its derivations name fields of its payload class, and
its settings are well formed. They live apart from the spec so that `agent.py` stays the
declaration. `Derived` and `Setting`, which they check, live here too, so that this module needs
nothing of `agent.py`; `agent.py` re-exports them and `SpecError`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import Derivation


class SpecError(Exception):
    """A description does not rebuild into an `AgentSpec` against this contract."""


@dataclass(frozen=True)
class Derived:
    """How an agent produces one payload field that it does not copy from input or evidence.

    `recorded_in` names a sibling field of type `Derivation` in which each value records how it
    actually came about, so a template fallback where a model would normally write is shown as
    template. Without it, `how` holds for every value.
    """

    how: Derivation
    recorded_in: str | None = None


@dataclass(frozen=True)
class Setting:
    """An option the agent offers, which a deployment's profile may set (`agent_settings`,
    docs/specs/policy-and-identity.md). `choices` are the values it accepts; `default` applies
    where the profile does not set it. The conductor refuses a profile value outside `choices`
    before the agent runs, and sends the agent the value that applies (`RunContext.settings`)."""

    choices: tuple[str, ...]
    default: str
    description: str = ""


DERIVATION_REF = "#/$defs/Derivation"


def _resolve(schema: Mapping[str, Any], node: Mapping[str, Any]) -> Mapping[str, Any]:
    """Follow `$ref` into the class schema's `$defs`, a list into its items, and an optional
    (`anyOf` with null) into the arm that is not null."""
    while True:
        ref = node.get("$ref")
        arms = [a for a in node.get("anyOf", ()) if a.get("type") != "null"]
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            node = schema.get("$defs", {}).get(ref.removeprefix("#/$defs/"), {})
        elif "items" in node:
            node = node["items"]
        elif len(arms) == 1:
            node = arms[0]
        else:
            return node


def _is_derivation(node: Mapping[str, Any]) -> bool:
    if node.get("$ref") == DERIVATION_REF:
        return True
    return any(_is_derivation(arm) for arm in node.get("anyOf", ()))


def check_derivation(
    agent_id: str, payload: ClassSchema | None, path: str, derived: Derived
) -> None:
    """A derivation names a field of the payload class's schema; `recorded_in` a Derivation."""
    where = f"agent {agent_id!r} derivation {path!r}"
    if payload is None:
        raise SpecError(f"{where}: the agent declares no payload")
    if not isinstance(derived.how, Derivation):
        raise SpecError(f"{where}: {derived.how!r} is not a Derivation")
    schema = payload.json_schema
    *parents, name = path.split(".")
    node: Mapping[str, Any] = schema
    holder = payload.name
    for part in parents:
        nested = _resolve(schema, node.get("properties", {}).get(part, {}))
        if "properties" not in nested:
            raise SpecError(f"{where}: {holder} has no nested field {part!r}")
        node, holder = nested, str(nested.get("title", part))
    properties = node.get("properties", {})
    if name not in properties:
        raise SpecError(f"{where}: {holder} has no field {name!r}")
    if derived.recorded_in is not None:
        recorder = properties.get(derived.recorded_in)
        if recorder is None or not _is_derivation(recorder):
            raise SpecError(f"{where}: {holder}.{derived.recorded_in} is not a Derivation field")


def check_setting(agent_id: str, name: str, setting: Setting) -> None:
    where = f"agent {agent_id!r} setting {name!r}"
    if not name or not isinstance(name, str):
        raise SpecError(f"{where}: a setting needs a name")
    if not setting.choices or not all(isinstance(c, str) and c for c in setting.choices):
        raise SpecError(f"{where}: choices must be one or more non-empty strings")
    if len(set(setting.choices)) != len(setting.choices):
        raise SpecError(f"{where}: a choice is listed more than once")
    if setting.default not in setting.choices:
        raise SpecError(f"{where}: default {setting.default!r} is not one of its choices")


# Enough code points for a ZWJ sequence or a skin tone, too few for a word.
ICON_MAX_CODE_POINTS = 8


def check_icon(agent_id: str, icon: str) -> None:
    """An agent's icon is empty or one emoji: short, with no whitespace and no ASCII letters or
    digits, so a name or a sentence cannot pass for one (docs/specs/agents.md)."""
    if not icon:
        return
    if (
        len(icon) > ICON_MAX_CODE_POINTS
        or any(c.isspace() for c in icon)
        or any(c.isascii() and c.isalnum() for c in icon)
    ):
        raise SpecError(f"agent {agent_id!r}: icon {icon!r} is not a single emoji")
