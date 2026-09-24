"""The shell is not run in CI; these tests check what can be checked without a browser.

The base `shell/uischema.json` covers the envelope. Each agent ships an RJSF fragment for its
payload in `spec.uischema`; the shell composes the two per render. The convention a fragment must
honour: a field a model may write points its badge at the sibling that records how the value
actually came about, so a template fallback is not badged as AI-derived.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_stub.agent import AbstainingStub
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import Derivation, GroundingMode, OutcomeStatus

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "shell" / "uischema.json").read_text(encoding="utf-8"))
INDEX = (ROOT / "shell" / "index.html").read_text(encoding="utf-8")

SPECS: list[AgentSpec] = [
    QualityReviewer.spec,
    FactChecker.spec,
    HelloWorld.spec,
    AbstainingStub.spec,
]


def _walk(node: Any, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], dict[str, Any]]:
    out: dict[tuple[str, ...], dict[str, Any]] = {}
    if isinstance(node, dict):
        if "ui:options" in node:
            out[path] = node["ui:options"]
        for k, v in node.items():
            if not k.startswith("ui:"):
                out.update(_walk(v, (*path, k)))
    return out


def _derivation_pairs(
    model: type[Any], path: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], str]]:
    """(path to field X, name of sibling X_derivation) for every pair the payload model declares."""
    out: list[tuple[tuple[str, ...], str]] = []
    fields = model.model_fields
    for name, info in fields.items():
        if name.endswith("_derivation") and name[: -len("_derivation")] in fields:
            out.append(((*path, name[: -len("_derivation")]), name))
        inner = getattr(info.annotation, "__args__", None)
        for candidate in inner or (info.annotation,):
            if hasattr(candidate, "model_fields"):
                # RJSF nests array items under an "items" key.
                sub_path = (*path, name, "items") if inner else (*path, name)
                out.extend(_derivation_pairs(candidate, sub_path))
    return out


@pytest.mark.parametrize("spec", [s for s in SPECS if s.payload_type], ids=lambda s: s.agent_id)
def test_model_writable_fields_point_at_their_derivation_sibling(spec: AgentSpec) -> None:
    assert spec.uischema is not None, f"{spec.agent_id} declares a payload but ships no fragment"
    declared = _walk(spec.uischema)
    assert spec.payload_type is not None
    for path, sibling in _derivation_pairs(spec.payload_type):
        assert path in declared, f"{spec.agent_id}: {'/'.join(path)} has no ui:options"
        assert declared[path].get("dd:derivation_field") == sibling, (spec.agent_id, path)


def test_derivation_values_are_from_the_contract_enum_or_verified() -> None:
    allowed = {d.value for d in Derivation} | {"verified"}
    for label, ui in [("base", BASE), *((s.agent_id, s.uischema) for s in SPECS if s.uischema)]:
        for path, opts in _walk(ui).items():
            if "dd:derivation" in opts:
                assert opts["dd:derivation"] in allowed, (label, path)


def test_base_uischema_covers_the_envelope_not_any_payload() -> None:
    assert "payload" not in BASE
    assert BASE["grounding_mode"]["ui:widget"] == "derivationBadge"


def test_shell_is_read_only_generic_and_pins_library_versions() -> None:
    assert BASE["ui:readonly"] is True
    assert "readonly: true" in INDEX
    assert "@rjsf/core@6.8.0?deps=react@19,react-dom@19" in INDEX
    assert "@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19" in INDEX
    assert 'lang="en-GB"' in INDEX and 'role="status"' in INDEX
    assert '<label for="agent-select">' in INDEX
    # Driven by the manifest and the samples listing; no agent or sample is named.
    assert 'fetch("/agents")' in INDEX and 'fetch("/samples")' in INDEX
    for name in ("r3.standards-advisor", "stub.abstain", "soil-chemistry", "FAIRsharing"):
        assert name not in INDEX, name


def test_every_outcome_status_has_a_colour_rule() -> None:
    for status in OutcomeStatus:
        assert f'[data-status="{status.value}"]' in INDEX, status


def _glossary_keys() -> set[str]:
    block = INDEX.split("// --- Glossary: BEGIN", 1)[1].split("// --- Glossary: END", 1)[0]
    return set(re.findall(r'^\s*"([^"]+)": \{ term: ', block, re.MULTILINE))


def test_glossary_explains_every_contract_value_the_page_shows() -> None:
    keys = _glossary_keys()
    assert "envelope" in keys
    expected = {f"status:{s.value}" for s in OutcomeStatus}
    expected |= {f"mode:{m.value}" for m in GroundingMode}
    expected |= {f"derivation:{d.value}" for d in Derivation} | {"derivation:verified"}
    assert expected <= keys, sorted(expected - keys)


def test_every_help_placeholder_names_a_glossary_entry() -> None:
    placeholders = set(re.findall(r'data-help="([^"]+)"', INDEX))
    assert placeholders, "the markup carries no help placeholders"
    assert placeholders <= _glossary_keys(), sorted(placeholders - _glossary_keys())
