"""The orchestrator's system prompt. Its prose is `system_prompt.md` beside this module, and the
Blueprint's process flow (`dd_sdk.process_flow`, docs/specs/orchestration.md) is appended to it. It
names no agent: the tools, built from the harness's manifest on each run, say which agents exist,
what each takes and which steps each serves. The flow names no requirement ID, so that the model
has none to repeat to a researcher (docs/specs/orchestration.md, invariant 14). So the prompt is
the same on every run and caches."""

from pathlib import Path

from dd_sdk.flow_prompt import describe_flow

PROSE = Path(__file__).with_name("system_prompt.md")

SYSTEM_PROMPT = PROSE.read_text(encoding="utf-8") + "\n" + describe_flow(requirements=False) + "\n"
