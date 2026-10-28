"""The orchestrator's system prompt. Its prose is `system_prompt.md` beside this module, and the
Blueprint's process flow (`dd_sdk.process_flow`, ADR-0028) is appended to it. It names no agent:
the tools, built from the harness's manifest on each run, say which agents exist, what each takes
and which Blueprint requirements each serves. So the prompt is the same on every run and caches."""

from pathlib import Path

from dd_sdk.process_flow import describe_flow

PROSE = Path(__file__).with_name("system_prompt.md")

SYSTEM_PROMPT = PROSE.read_text(encoding="utf-8") + "\n" + describe_flow() + "\n"
