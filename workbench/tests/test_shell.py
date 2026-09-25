"""The shell is not run in CI; these tests check what can be checked without a browser.

The base `shell/uischema.json` covers the envelope. Each agent ships an RJSF fragment for its
payload in `spec.uischema`; the shell composes the two per render. The convention a fragment must
honour: a field a model may write points its badge at the sibling that records how the value
actually came about, so a template fallback is not badged as AI-derived.

The shell is two pages (Inspect, Chat) sharing one stylesheet and a set of ES modules; the
string checks below read all of them together.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from dd_agent_director.agent import DirectorStub
from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_stub.agent import AbstainingStub
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import Derivation, GroundingMode, OutcomeStatus

ROOT = Path(__file__).resolve().parents[1]
SHELL_DIR = ROOT / "shell"
BASE = json.loads((SHELL_DIR / "uischema.json").read_text(encoding="utf-8"))
PAGES = {n: (SHELL_DIR / n).read_text(encoding="utf-8") for n in ("index.html", "chat.html")}
SOURCES = sorted([*SHELL_DIR.glob("*.html"), *SHELL_DIR.glob("*.css"), *SHELL_DIR.glob("js/*.js")])
SHELL = "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)
GLOSSARY_JS = (SHELL_DIR / "js" / "glossary.js").read_text(encoding="utf-8")

SPECS: list[AgentSpec] = [
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
    assert "readonly: true" in SHELL
    assert "@rjsf/core@6.8.0?deps=react@19,react-dom@19" in SHELL
    assert "@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19" in SHELL
    assert 'role="status"' in PAGES["index.html"] and 'role="status"' in PAGES["chat.html"]
    assert '<label for="agent-select">' in SHELL
    # Driven by the manifest and the samples listing; no agent or sample is named.
    assert 'fetch("/agents")' in SHELL and 'fetch("/samples")' in SHELL
    for name in (
        "r3.standards-advisor",
        "stub.abstain",
        "director.stub",
        "soil-chemistry",
        "FAIRsharing",
    ):
        assert name not in SHELL, name


def test_input_form_is_built_from_the_input_schema_and_names_no_class() -> None:
    form = (SHELL_DIR / "js" / "inputform.js").read_text(encoding="utf-8")
    assert "@rjsf/core@6.8.0?deps=react@19,react-dom@19" in form
    assert "@rjsf/validator-ajv8@6.8.0?deps=react@19,react-dom@19" in form
    assert 'tagName: "div"' in form  # Chat's composer is a <form>; forms do not nest
    for page in ("inspect.js", "chat.js"):
        module = (SHELL_DIR / "js" / page).read_text(encoding="utf-8")
        assert 'fetch("/schema/invocation_request.schema.json")' in module, page
        assert 'from "./inputform.js"' in module, page
    # Chat names Message for its text box; no other input class is named anywhere.
    for name in ("Salutation", "Claim", "MetadataRecord", "DatasetProfile"):
        assert name not in SHELL, name
    assert 'id="chat-json"' not in PAGES["chat.html"]


@pytest.mark.requirement("DD-CONVERSATION")
def test_chat_mode_is_driven_by_the_conversation_api_and_names_every_agent_version() -> None:
    assert '<label for="chat-agent-select">' in PAGES["chat.html"]
    assert 'fetch("/conversations")' in SHELL and "fetch(`/conversations/${" in SHELL
    # Every reply card, and every delegated card inside it, is labelled agent_id@agent_version.
    assert "`${env.agent_id}@${env.agent_version}`" in SHELL
    assert "version_changes" in SHELL
    # The orchestrator is found by grounding mode, never by name.
    assert 'grounding_mode === "delegation"' in SHELL
    # Chat and Inspect both reload from the address bar; Inspect forwards the old Chat address.
    assert "/shell/chat.html?conversation_id=" in SHELL and "/shell/?invocation_id=" in SHELL
    assert 'p.get("mode") === "chat"' in PAGES["index.html"]


def test_every_outcome_status_has_a_colour_rule() -> None:
    for status in OutcomeStatus:
        assert f'[data-status="{status.value}"]' in SHELL, status


def _glossary_keys() -> set[str]:
    block = GLOSSARY_JS.split("// --- Glossary: BEGIN", 1)[1].split("// --- Glossary: END", 1)[0]
    return set(re.findall(r'^\s*"([^"]+)": \{ term: ', block, re.MULTILINE))


def test_glossary_explains_every_contract_value_the_page_shows() -> None:
    keys = _glossary_keys()
    assert "envelope" in keys
    expected = {f"status:{s.value}" for s in OutcomeStatus}
    expected |= {f"mode:{m.value}" for m in GroundingMode}
    expected |= {f"derivation:{d.value}" for d in Derivation} | {"derivation:verified"}
    assert expected <= keys, sorted(expected - keys)


def test_every_help_placeholder_names_a_glossary_entry() -> None:
    placeholders = set(re.findall(r'data-help="([^"]+)"', SHELL))
    assert placeholders, "the markup carries no help placeholders"
    assert placeholders <= _glossary_keys(), sorted(placeholders - _glossary_keys())


def _mode_nav(page: str) -> str:
    return page.split('<nav class="modes"', 1)[1].split("</nav>", 1)[0]


def test_both_pages_share_the_mode_tabs_and_mark_their_own() -> None:
    nav = {name: _mode_nav(page) for name, page in PAGES.items()}
    unmarked = {name: text.replace(' aria-current="page"', "") for name, text in nav.items()}
    assert unmarked["index.html"] == unmarked["chat.html"]
    assert re.search(r'href="/shell/" aria-current="page"', nav["index.html"])
    assert re.search(r'href="/shell/chat.html" aria-current="page"', nav["chat.html"])
    for name, page in PAGES.items():
        assert nav[name].count('aria-current="page"') == 1, name
        assert 'lang="en-GB"' in page, name
        assert 'id="glossary"' in page, name


def test_every_shell_path_a_page_or_module_references_exists() -> None:
    paths = set(re.findall(r'(?:href|src)="/shell/([^"?#]+)"', SHELL))
    paths |= {f"js/{m}" for m in re.findall(r'from "\./([^"]+)"', SHELL)}
    assert paths, "no shell paths referenced"
    for path in paths:
        assert (SHELL_DIR / path).is_file(), path


# --- Icons --------------------------------------------------------------------------------
# Lucide icons come from the vendored sprite shell/icons.svg (scripts/build_icons.py). They follow
# https://lucide.dev/how-to/accessibility: decorative, hidden from assistive technology, beside
# visible text or inside a control that carries its own label.
SPRITE = (SHELL_DIR / "icons.svg").read_text(encoding="utf-8")
COMMON_JS = (SHELL_DIR / "js" / "common.js").read_text(encoding="utf-8")


def _icon_map(name: str) -> dict[str, str]:
    body = re.search(rf"{name} = \{{([^}}]*)\}}", SHELL)
    assert body, f"{name} not found"
    return dict(re.findall(r'(\w+): "([a-z0-9-]+)"', body.group(1)))


def test_every_outcome_status_has_an_icon() -> None:
    icons = _icon_map("STATUS_ICONS")
    for status in OutcomeStatus:
        assert status.value in icons, status
    assert len(set(icons.values())) == len(icons), "two statuses share an icon"


def test_every_icon_the_shell_uses_is_in_the_sprite() -> None:
    symbols = set(re.findall(r'<symbol id="([a-z0-9-]+)"', SPRITE))
    used = set(re.findall(r'icons\.svg#([a-z0-9-]+)"', SHELL))
    used |= set(re.findall(r'icon\("([a-z0-9-]+)"\)', SHELL))
    used |= set(_icon_map("STATUS_ICONS").values()) | set(_icon_map("FACT_ICONS").values())
    assert used, "the shell uses no icons"
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
    assert "ISC License" in (SHELL_DIR / "icons.LICENCE").read_text(encoding="utf-8")
    assert "see icons.LICENCE" in SPRITE
