"""The shell is not run in CI; these tests check what can be checked without a browser."""

from __future__ import annotations

import json
from pathlib import Path

from workbench.contract.models import Derivation

ROOT = Path(__file__).resolve().parents[1]
UISCHEMA = json.loads((ROOT / "shell" / "uischema.json").read_text(encoding="utf-8"))
INDEX = (ROOT / "shell" / "index.html").read_text(encoding="utf-8")


def _walk(node: object, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], dict]]:  # type: ignore[type-arg]
    out = []
    if isinstance(node, dict):
        if "ui:options" in node:
            out.append((path, node["ui:options"]))
        for k, v in node.items():
            if not k.startswith("ui:"):
                out.extend(_walk(v, (*path, k)))
    return out


def test_every_model_derived_field_declares_a_derivation_field() -> None:
    """Fields a model may write must point the badge at the sibling that records how the value
    actually came about, so a template fallback is not badged as AI-derived."""
    declared = dict(_walk(UISCHEMA))
    rationale = declared[("payload", "items", "items", "rationale")]
    assert rationale["dd:derivation"] == "model"
    assert rationale["dd:derivation_field"] == "rationale_derivation"
    kind = declared[("payload", "items", "items", "kind")]
    assert kind["dd:derivation_field"] == "classification_derivation"


def test_derivation_values_are_from_the_contract_enum_or_verified() -> None:
    allowed = {d.value for d in Derivation} | {"verified"}
    for path, opts in _walk(UISCHEMA):
        if "dd:derivation" in opts:
            assert opts["dd:derivation"] in allowed, path


def test_shell_is_read_only_and_pins_library_versions() -> None:
    assert UISCHEMA["ui:readonly"] is True
    assert "readonly: true" in INDEX
    assert "@rjsf/core@6.8.0?deps=react@19,react-dom@19" in INDEX
    assert "@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19" in INDEX
    assert 'lang="en-GB"' in INDEX and 'role="status"' in INDEX
