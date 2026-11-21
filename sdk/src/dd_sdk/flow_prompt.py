"""The process flow as plain text for an orchestrator's prompt (`describe_flow`).

Split from `process_flow`, which holds the Blueprint data, to keep that module under the size limit.
"""

from __future__ import annotations

import re

from dd_sdk.process_flow import ENTRIES, PHASES

# A Blueprint requirement ID such as R5 or R3.1: for traceability, never in what a researcher
# reads (docs/specs/orchestration.md, invariant 14). Tests use it to check replies and prompts.
REQUIREMENT_ID = re.compile(r"\bR\d+(?:\.\d+)?\b")


def describe_flow(*, requirements: bool = True) -> str:
    """The entry points and phases as plain text, for a model's prompt. With `requirements`
    False, a step does not name the Blueprint requirements it applies: a model that talks to
    researchers is not shown codes it might repeat to them (docs/specs/orchestration.md,
    invariant 14)."""
    lines = ["Entry points:"]
    lines += [f"- Entry {e.number}: {e.text}. Starts at Phase {e.starts_at}." for e in ENTRIES]
    lines.append("All three continue through every later phase.")
    for phase in PHASES:
        lines.append("")
        lines.append(f"Phase {phase.number}: {phase.title}")
        for step in phase.steps:
            notes: list[str] = []
            if requirements:
                notes.append(", ".join(step.requirements) or "no requirement")
            if step.optional:
                notes.append("optional")
            if step.out_of_scope:
                notes.append("out of scope for now: say so, and do not offer to do it")
            suffix = f" ({'; '.join(notes)})" if notes else ""
            lines.append(f"- [{step.id}] {step.text}{suffix}")
    return "\n".join(lines)
