"""The agent card that `@data-director/agent-view` (sdk/browser) is tested against.

The card `dd_sdk.serve.agent_card` builds for this suite's own agent specification
(`test_agent_spec.SPEC`), serialised as it is served at `/.well-known/agent-card.json`, is kept
in `browser/tests/fixtures/`. A change to how cards are built changes the fixture: outside CI the
test rewrites it, and in CI a stale fixture fails (`DD_WRITE_FIXTURES` overrides either way).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from test_agent_spec import SPEC

from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.models import InvocationRequest
from dd_sdk.serve import agent_card

FIXTURE = Path(__file__).resolve().parents[1] / "browser/tests/fixtures/agent-card.json"


@dataclass
class _Agent:
    spec: AgentSpec

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        raise NotImplementedError


def _rewrite() -> bool:
    if "DD_WRITE_FIXTURES" in os.environ:
        return os.environ["DD_WRITE_FIXTURES"] == "1"
    return not os.environ.get("CI")


def test_the_agent_card_fixture_is_what_an_agent_serves() -> None:
    card = MessageToDict(agent_card(_Agent(SPEC), "http://agent.example"))
    text = json.dumps(card, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    held = json.loads(FIXTURE.read_text("utf-8")) if FIXTURE.exists() else None
    if held == json.loads(text):
        return
    if _rewrite():
        FIXTURE.write_text(text, "utf-8")
        return
    raise AssertionError(
        f"{FIXTURE.name} is stale. Run `uv run pytest sdk/tests/test_agent_view_fixtures.py` "
        "locally, which rewrites it, and commit the result."
    )
