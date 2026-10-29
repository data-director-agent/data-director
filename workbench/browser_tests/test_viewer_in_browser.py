"""The viewer in a real browser (#9): each page renders what the app serves it.

`workbench/tests/test_viewer.py` checks the viewer's files; these tests load the pages in
Chromium against the workbench app and check what a person sees: the outcome, the derivation
badges, the evidence table and its cited markers, a replayed run and a delegated chat turn.

No test here carries a requirement marker. The viewer is a development tool, not the reference
implementation, so what it shows substantiates no requirement; the envelopes it draws are
checked by the marked tests in `workbench/tests/` and `harness/tests/`.

Run with `uv run pytest workbench/browser_tests` after `uv run playwright install chromium`.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

# Generous, because the first page in a session compiles React and RJSF.
TIMEOUT_MS = 15_000


def open_inspect(viewer: Page, server_url: str, agent_id: str, sample: str | None) -> None:
    viewer.goto(f"{server_url}/viewer/inspect.html")
    expect(viewer.locator("#status")).to_have_text("Ready.", timeout=TIMEOUT_MS)
    viewer.select_option("#agent-select", agent_id)
    if sample is not None:
        viewer.select_option("#sample-select", sample)
    expect(viewer.locator("#run")).to_be_enabled(timeout=TIMEOUT_MS)


def outcome(viewer: Page, status: str) -> None:
    """The run outcome panel shows `status`."""
    pill = viewer.locator("#outcome-head .pill")
    expect(pill).to_have_attribute("data-status", status, timeout=TIMEOUT_MS)


def test_inspect_runs_hello_world_and_badges_its_template_field(
    viewer: Page, server_url: str
) -> None:
    open_inspect(viewer, server_url, "example.hello", "hello.salutation.json")
    viewer.locator("#run").click()
    expect(viewer.locator("#status")).to_have_text(re.compile(r"^Completed "), timeout=TIMEOUT_MS)
    outcome(viewer, "succeeded")
    expect(viewer.locator("#facts")).to_contain_text("example.hello@")
    expect(viewer.locator("#payload-class")).to_have_text("Greeting")
    expect(viewer.locator("#form")).to_contain_text("Hello, world!", timeout=TIMEOUT_MS)
    # greeting_text is declared template, recorded in greeting_derivation, which is hidden.
    expect(viewer.locator("#form .badge.template")).to_have_count(1)
    expect(viewer.locator("#form")).not_to_contain_text("greeting_derivation")
    # The input was sent from this tab, so it is shown rather than its hash.
    expect(viewer.locator("#input")).to_contain_text("world")
    expect(viewer).to_have_url(re.compile(r"\?invocation_id="))


def test_inspect_shows_an_abstention_without_a_payload(viewer: Page, server_url: str) -> None:
    open_inspect(viewer, server_url, "stub.abstain", None)
    viewer.keyboard.press("Control+Enter")
    outcome(viewer, "abstained")
    expect(viewer.locator("#outcome-head .statement")).not_to_be_empty()
    expect(viewer.locator("#payload-class")).to_have_text("")
    expect(viewer.locator("#form .badge")).to_have_count(0)


def test_inspect_marks_the_evidence_the_payload_cites(viewer: Page, server_url: str) -> None:
    open_inspect(viewer, server_url, "advisor.standards", "soil-chemistry.profile.json")
    viewer.locator("#run").click()
    outcome(viewer, "succeeded")
    rows = viewer.locator("#evidence tbody tr")
    expect(rows.first).to_be_visible(timeout=TIMEOUT_MS)
    expect(rows.filter(has_text="cited").first).to_be_visible()
    expect(viewer.locator("#form .badge.lexical").first).to_be_visible(timeout=TIMEOUT_MS)
    expect(viewer.locator("#telemetry")).to_contain_text("trace_id")


def test_a_stored_run_replays_by_invocation_id(viewer: Page, server_url: str) -> None:
    open_inspect(viewer, server_url, "advisor.quality", "orda-record.metadata.json")
    viewer.locator("#run").click()
    outcome(viewer, "succeeded")
    url = viewer.url
    invocation_id = url.split("invocation_id=", 1)[1]

    # A fresh tab holds no input, so the replay comes only from the run store over AG-UI.
    replay = viewer.context.new_page()
    replay.goto(url)
    outcome(replay, "succeeded")
    expect(replay.locator("#status")).to_have_text(re.compile(r"^Showing "))
    expect(replay.locator("#facts")).to_contain_text(invocation_id)
    expect(replay.locator("#input")).to_contain_text("Input not stored with the envelope.")
    expect(replay.locator("#tab-input")).to_be_hidden()
    expect(replay.locator(f'#history button[data-id="{invocation_id}"]')).to_have_attribute(
        "aria-current", "true"
    )

    # The Envelope JSON tab holds the same run, reached from the keyboard.
    replay.locator("#tab-overview").focus()
    replay.keyboard.press("ArrowRight")
    expect(replay.locator("#tab-envelope")).to_be_focused()
    expect(replay.locator("#envelope-json")).to_contain_text(f'"invocation_id": "{invocation_id}"')


def test_a_replay_of_an_unknown_run_says_so(
    viewer: Page, server_url: str, page_errors: list[str]
) -> None:
    viewer.goto(
        f"{server_url}/viewer/inspect.html?invocation_id=01a00000-0000-7000-8000-000000000000"
    )
    expect(viewer.locator("#status")).to_have_text(
        re.compile(r"^No stored run "), timeout=TIMEOUT_MS
    )
    expect(viewer.locator("#result")).to_be_hidden()
    # The replay endpoint answers 404, which the browser logs; nothing else may go wrong.
    assert page_errors == [
        "console: Failed to load resource: the server responded with a status of 404 (Not Found)"
    ]
    page_errors.clear()


def test_chat_shows_the_orchestrator_delegating(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/")
    # The orchestrator is chosen by default, by its grounding mode.
    expect(viewer.locator("#chat-agent-select")).to_have_value(
        "orchestrator.stub", timeout=TIMEOUT_MS
    )
    viewer.locator("#chat-text").fill("hello world")
    viewer.locator("#send").click()
    reply = viewer.locator("#transcript article.card").first
    expect(reply).to_have_attribute("aria-label", re.compile(r"^orchestrator\.stub@.* succeeded$"))
    expect(reply.locator(".reply")).to_contain_text("example.hello", timeout=TIMEOUT_MS)
    children = reply.get_by_role("list", name="Delegated invocations")
    expect(children).to_contain_text("example.hello@")
    expect(viewer.locator("#chat-agent-select")).to_be_disabled()
    expect(viewer).to_have_url(re.compile(r"\?conversation_id="))


def test_the_glossary_opens_and_closes_from_the_keyboard(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/inspect.html")
    expect(viewer.locator("#status")).to_have_text("Ready.", timeout=TIMEOUT_MS)
    viewer.locator("#open-glossary").click()
    dialog = viewer.get_by_role("dialog", name="Glossary")
    expect(dialog).to_be_visible()
    expect(dialog.locator("dt").first).to_be_visible()
    viewer.keyboard.press("Escape")
    expect(dialog).to_be_hidden()


def test_the_agents_page_lists_every_registered_agent(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/agents.html")
    for agent_id in (
        "orchestrator.stub",
        "example.hello",
        "advisor.quality",
        "advisor.standards",
        "stub.abstain",
    ):
        row = viewer.locator(f'#agent-list button[data-id="{agent_id}"]')
        expect(row).to_contain_text("available", timeout=TIMEOUT_MS)


def test_the_agents_page_lays_out_the_agent_card_to_read(viewer: Page, server_url: str) -> None:
    viewer.goto(f"{server_url}/viewer/agents.html?agent_id=orchestrator.stub")
    card = viewer.locator("#agent-card .agent-card")
    expect(card).to_be_visible(timeout=TIMEOUT_MS)
    for heading in ("Interfaces", "Capabilities", "Extensions", "Security", "Skills"):
        expect(card.get_by_role("heading", name=heading, exact=True)).to_be_visible()
    # The agent-spec extension's params, field by field, and the skill's tags.
    expect(card).to_contain_text("grounding mode")
    expect(card).to_contain_text("delegation")
    expect(card).to_contain_text("accepts:Message")
    # The raw card stays, collapsed until asked for.
    raw = viewer.locator("#agent-card-json")
    expect(raw).to_be_hidden()
    viewer.locator("details.raw-json > summary").click()
    expect(raw).to_contain_text('"supportedInterfaces"')
