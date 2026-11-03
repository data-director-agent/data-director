"""The viewer against WCAG 2.2 AA in a real browser (#85): axe-core in light and dark, and reflow.

Each state a person reaches is checked with the same axe rule tags as the app shell's browser
tests (`app/web/e2e`): Chat before and after a turn, Inspect after a run, the Glossary dialog
and the Agents page with a card open. Each is also checked for reflow: at 320 CSS pixels wide,
the 400% zoom equivalent of WCAG 1.4.10, the page must not scroll sideways. Keyboard paths are in
`test_viewer_in_browser.py`.

`.github/workflows/accessibility.yml` runs this module; the CI workflow's viewer job leaves it to
that workflow. Run it with `uv run pytest workbench/browser_tests/test_viewer_accessibility.py`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect

# Generous, because the first page in a session compiles React and RJSF.
TIMEOUT_MS = 15_000
# The same tags as app/web/e2e/shell.spec.ts: WCAG 2.0, 2.1 and 2.2, levels A and AA.
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
# WCAG 1.4.10 Reflow: 320 CSS pixels is 1280 at 400% zoom.
REFLOW_WIDTH = 320

Scheme = Literal["light", "dark"]


def violations(page: Page) -> list[str]:
    """Each element axe finds in violation, with the rule and what it measured."""
    options = {"runOnly": {"type": "tag", "values": WCAG_TAGS}}
    found: list[dict[str, Any]] = Axe().run(page, options=options).response["violations"]
    return [
        f"{v['id']} {node['target']}: {' '.join(node['failureSummary'].split())}"
        for v in found
        for node in v["nodes"]
    ]


def overflow(page: Page) -> int:
    """How far the page scrolls sideways, in CSS pixels, at the reflow width."""
    size = page.viewport_size
    page.set_viewport_size({"width": REFLOW_WIDTH, "height": size["height"] if size else 800})
    width: int = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    if size:
        page.set_viewport_size(size)
    return width


def chat(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/")
    expect(viewer.locator("#chat-agent-select")).to_have_value(
        "orchestrator.stub", timeout=TIMEOUT_MS
    )


def chat_after_a_turn(viewer: Page, server_url: str) -> None:
    chat(viewer, server_url)
    viewer.locator("#chat-text").fill("hello world")
    viewer.locator("#send").click()
    reply = viewer.locator("#transcript article.card").first
    expect(reply.locator(".reply")).to_contain_text("example.hello", timeout=TIMEOUT_MS)


def inspect_after_a_run(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/inspect.html")
    expect(viewer.locator("#status")).to_have_text("Ready.", timeout=TIMEOUT_MS)
    viewer.select_option("#agent-select", "advisor.standards")
    viewer.select_option("#sample-select", "soil-chemistry.profile.json")
    expect(viewer.locator("#run")).to_be_enabled(timeout=TIMEOUT_MS)
    viewer.locator("#run").click()
    expect(viewer.locator("#status")).to_have_text(re.compile(r"^Completed "), timeout=TIMEOUT_MS)
    expect(viewer.locator("#evidence tbody tr").first).to_be_visible(timeout=TIMEOUT_MS)
    # The payload renders after the outcome; it holds the widest content on the page.
    expect(viewer.locator("#form .badge.lexical").first).to_be_visible(timeout=TIMEOUT_MS)


def glossary(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/inspect.html")
    expect(viewer.locator("#status")).to_have_text("Ready.", timeout=TIMEOUT_MS)
    viewer.locator("#open-glossary").click()
    expect(viewer.get_by_role("dialog", name="Glossary")).to_be_visible()


def agents_with_a_card(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/agents.html?agent_id=orchestrator.stub")
    expect(viewer.locator("#agent-card .agent-card")).to_be_visible(timeout=TIMEOUT_MS)
    expect(viewer.locator('#agent-list button[data-id="example.hello"]')).to_contain_text(
        "available", timeout=TIMEOUT_MS
    )


STATES: dict[str, Callable[[Page, str], None]] = {
    "chat": chat,
    "chat after a turn": chat_after_a_turn,
    "inspect after a run": inspect_after_a_run,
    "glossary": glossary,
    "agents with a card": agents_with_a_card,
}


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("state", STATES)
def test_no_axe_violations_against_wcag_2_2_aa(
    viewer: Page, server_url: str, state: str, scheme: Scheme
) -> None:
    viewer.emulate_media(color_scheme=scheme)
    STATES[state](viewer, server_url)
    assert violations(viewer) == []


@pytest.mark.parametrize("state", STATES)
def test_reflows_at_320_css_pixels(viewer: Page, server_url: str, state: str) -> None:
    STATES[state](viewer, server_url)
    assert overflow(viewer) == 0
