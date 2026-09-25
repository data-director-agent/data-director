"""The viewer is not run in CI; these tests check what can be checked without a browser.

The base `viewer/uischema.json` covers the envelope. A payload's uiSchema is worked out in the
viewer from the payload class's schema and the agent's `spec.derivations` (ADR-0016); no agent
ships presentation. The convention the derivations must honour: every field that records how a
value came about is named as some field's `recorded_in`, so a template fallback where a model may
write is not badged as AI-derived.

The viewer is two pages (Inspect, Chat) sharing one stylesheet and a set of ES modules; the
string checks below read all of them together.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, get_args

import pytest

from dd_agent_director.agent import DirectorStub
from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_r3.agent import R3Agent
from dd_agent_stub.agent import AbstainingStub
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import Assurance, Derivation, GroundingMode, OutcomeStatus

ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = ROOT / "viewer"
BASE = json.loads((VIEWER_DIR / "uischema.json").read_text(encoding="utf-8"))
PAGES = {n: (VIEWER_DIR / n).read_text(encoding="utf-8") for n in ("index.html", "chat.html")}
SOURCES = sorted(
    [*VIEWER_DIR.glob("*.html"), *VIEWER_DIR.glob("*.css"), *VIEWER_DIR.glob("js/*.js")]
)
VIEWER = "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)
GLOSSARY_JS = (VIEWER_DIR / "js" / "glossary.js").read_text(encoding="utf-8")

SPECS: list[AgentSpec] = [
    R3Agent.spec,
    QualityReviewer.spec,
    FactChecker.spec,
    HelloWorld.spec,
    AbstainingStub.spec,
    DirectorStub.spec,
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


def _derivation_fields(model: type[Any], prefix: str = "") -> set[tuple[str, str]]:
    """(parent path, field name) for every field of type Derivation in the payload model."""
    out: set[tuple[str, str]] = set()
    for name, info in model.model_fields.items():
        candidates = get_args(info.annotation) or (info.annotation,)
        if Derivation in candidates:
            out.add((prefix, name))
        for candidate in candidates:
            for inner in get_args(candidate) or (candidate,):
                if isinstance(inner, type) and hasattr(inner, "model_fields"):
                    out |= _derivation_fields(inner, f"{prefix}{name}.")
    return out


@pytest.mark.parametrize("spec", [s for s in SPECS if s.payload], ids=lambda s: s.agent_id)
def test_every_derivation_field_is_what_some_declared_field_is_recorded_in(
    spec: AgentSpec,
) -> None:
    assert spec.payload is not None and spec.payload.model is not None
    recorders = {
        (path.rpartition(".")[0] + "." if "." in path else "", d.recorded_in)
        for path, d in spec.derivations.items()
        if d.recorded_in
    }
    assert _derivation_fields(spec.payload.model) <= recorders, spec.agent_id


def test_base_derivation_values_are_from_the_contract_enum_or_verified() -> None:
    allowed = {d.value for d in Derivation} | {"verified"}
    for path, opts in _walk(BASE).items():
        if "dd:derivation" in opts:
            assert opts["dd:derivation"] in allowed, path


def test_payload_presentation_is_worked_out_from_schema_and_derivations() -> None:
    assert "uiSchema: payloadUi(ps, derivations)" in VIEWER
    assert "agents[envelope.agent_id]?.derivations" in VIEWER
    assert "uischema" not in (VIEWER_DIR / "js" / "inspect.js").read_text(encoding="utf-8")


def test_base_uischema_covers_the_envelope_not_any_payload() -> None:
    assert "payload" not in BASE
    assert BASE["grounding_mode"]["ui:widget"] == "derivationBadge"


def test_shell_is_read_only_generic_and_pins_library_versions() -> None:
    assert BASE["ui:readonly"] is True
    assert "readonly: true" in VIEWER
    assert "@rjsf/core@6.8.0?deps=react@19,react-dom@19" in VIEWER
    assert "@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19" in VIEWER
    assert 'role="status"' in PAGES["index.html"] and 'role="status"' in PAGES["chat.html"]
    assert '<label for="agent-select">' in VIEWER
    # Driven by the manifest and the samples listing; no agent or sample is named.
    assert 'fetch("/agents")' in VIEWER and 'fetch("/samples")' in VIEWER
    for name in (
        "r3.standards-advisor",
        "stub.abstain",
        "director.stub",
        "soil-chemistry",
        "FAIRsharing",
    ):
        assert name not in VIEWER, name


def test_input_form_is_built_from_the_input_schema_and_names_no_class() -> None:
    form = (VIEWER_DIR / "js" / "inputform.js").read_text(encoding="utf-8")
    assert "@rjsf/core@6.8.0?deps=react@19,react-dom@19" in form
    assert "@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19" in form
    assert 'tagName: "div"' in form  # Chat's composer is a <form>; forms do not nest
    for page in ("inspect.js", "chat.js"):
        module = (VIEWER_DIR / "js" / page).read_text(encoding="utf-8")
        assert 'fetch("/schema/invocation_request.schema.json")' in module, page
        assert 'from "./inputform.js"' in module, page
    # Chat names Message for its text box; no other input class is named anywhere.
    for name in ("Salutation", "Claim", "MetadataRecord", "DatasetProfile"):
        assert name not in VIEWER, name
    assert 'id="chat-json"' not in PAGES["chat.html"]


@pytest.mark.requirement("DD-CONVERSATION")
def test_chat_mode_is_driven_by_the_conversation_api_and_names_every_agent_version() -> None:
    assert '<label for="chat-agent-select">' in PAGES["chat.html"]
    assert 'fetch("/conversations")' in VIEWER and "fetch(`/conversations/${" in VIEWER
    # Every reply card, and every delegated card inside it, is labelled agent_id@agent_version.
    assert "`${env.agent_id}@${env.agent_version}`" in VIEWER
    assert "version_changes" in VIEWER
    # The orchestrator is found by grounding mode, never by name.
    assert 'grounding_mode === "delegation"' in VIEWER
    # Chat and Inspect both reload from the address bar; Inspect forwards the old Chat address.
    assert "/viewer/chat.html?conversation_id=" in VIEWER and "/viewer/?invocation_id=" in VIEWER
    assert 'p.get("mode") === "chat"' in PAGES["index.html"]


def test_every_outcome_status_has_a_colour_rule() -> None:
    for status in OutcomeStatus:
        assert f'[data-status="{status.value}"]' in VIEWER, status


def _glossary_keys() -> set[str]:
    block = GLOSSARY_JS.split("// --- Glossary: BEGIN", 1)[1].split("// --- Glossary: END", 1)[0]
    return set(re.findall(r'^\s*"([^"]+)": \{ term: ', block, re.MULTILINE))


def test_glossary_explains_every_contract_value_the_page_shows() -> None:
    keys = _glossary_keys()
    assert "envelope" in keys
    expected = {f"status:{s.value}" for s in OutcomeStatus}
    expected |= {f"mode:{m.value}" for m in GroundingMode}
    expected |= {f"derivation:{d.value}" for d in Derivation} | {"derivation:verified"}
    expected |= {f"assurance:{a.value}" for a in Assurance} | {"acting_for"}
    assert expected <= keys, sorted(expected - keys)


def test_every_help_placeholder_names_a_glossary_entry() -> None:
    placeholders = set(re.findall(r'data-help="([^"]+)"', VIEWER))
    assert placeholders, "the markup carries no help placeholders"
    assert placeholders <= _glossary_keys(), sorted(placeholders - _glossary_keys())


def _mode_nav(page: str) -> str:
    return page.split('<nav class="modes"', 1)[1].split("</nav>", 1)[0]


def test_both_pages_share_the_mode_tabs_and_mark_their_own() -> None:
    nav = {name: _mode_nav(page) for name, page in PAGES.items()}
    unmarked = {name: text.replace(' aria-current="page"', "") for name, text in nav.items()}
    assert unmarked["index.html"] == unmarked["chat.html"]
    assert re.search(r'href="/viewer/" aria-current="page"', nav["index.html"])
    assert re.search(r'href="/viewer/chat.html" aria-current="page"', nav["chat.html"])
    for name, page in PAGES.items():
        assert nav[name].count('aria-current="page"') == 1, name
        assert 'lang="en-GB"' in page, name
        assert 'id="glossary"' in page, name


def test_every_shell_path_a_page_or_module_references_exists() -> None:
    paths = set(re.findall(r'(?:href|src)="/viewer/([^"?#]+)"', VIEWER))
    paths |= {f"js/{m}" for m in re.findall(r'from "\./([^"]+)"', VIEWER)}
    assert paths, "no viewer paths referenced"
    for path in paths:
        assert (VIEWER_DIR / path).is_file(), path


# --- Icons --------------------------------------------------------------------------------
# Lucide icons come from the vendored sprite viewer/icons.svg (scripts/build_icons.py). They follow
# https://lucide.dev/how-to/accessibility: decorative, hidden from assistive technology, beside
# visible text or inside a control that carries its own label.
SPRITE = (VIEWER_DIR / "icons.svg").read_text(encoding="utf-8")
COMMON_JS = (VIEWER_DIR / "js" / "common.js").read_text(encoding="utf-8")


def _icon_map(name: str) -> dict[str, str]:
    body = re.search(rf"{name} = \{{([^}}]*)\}}", VIEWER)
    assert body, f"{name} not found"
    return dict(re.findall(r'(\w+): "([a-z0-9-]+)"', body.group(1)))


def test_every_outcome_status_has_an_icon() -> None:
    icons = _icon_map("STATUS_ICONS")
    for status in OutcomeStatus:
        assert status.value in icons, status
    assert len(set(icons.values())) == len(icons), "two statuses share an icon"


def test_every_icon_the_shell_uses_is_in_the_sprite() -> None:
    symbols = set(re.findall(r'<symbol id="([a-z0-9-]+)"', SPRITE))
    used = set(re.findall(r'icons\.svg#([a-z0-9-]+)"', VIEWER))
    used |= set(re.findall(r'icon\("([a-z0-9-]+)"\)', VIEWER))
    used |= set(_icon_map("STATUS_ICONS").values()) | set(_icon_map("FACT_ICONS").values())
    assert used, "the viewer uses no icons"
    assert used <= symbols, sorted(used - symbols)


def test_icons_are_hidden_from_assistive_technology() -> None:
    for name, page in PAGES.items():
        tags = re.findall(r'<svg class="icon"[^>]*>', page)
        assert tags, name
        for tag in tags:
            assert 'aria-hidden="true"' in tag and 'focusable="false"' in tag, (name, tag)
            assert "aria-label" not in tag, (name, tag)
    assert 'svg.setAttribute("aria-hidden", "true")' in COMMON_JS
    assert 'svg.setAttribute("focusable", "false")' in COMMON_JS
    assert "<title" not in SPRITE and "aria-label" not in SPRITE


def test_icon_sprite_ships_its_licence() -> None:
    assert "ISC License" in (VIEWER_DIR / "icons.LICENCE").read_text(encoding="utf-8")
    assert "see icons.LICENCE" in SPRITE
