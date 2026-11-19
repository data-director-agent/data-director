"""The process flow as plain text for an orchestrator's prompt (`describe_flow`).

Split from `process_flow`, which holds the Blueprint data, to keep that module under the size limit.
"""

from __future__ import annotations

from dd_sdk.process_flow import ENTRIES, PHASES


def describe_flow() -> str:
    """The entry points and phases as plain text, for a model's prompt."""
    lines = ["Entry points:"]
    lines += [f"- Entry {e.number}: {e.text}. Starts at Phase {e.starts_at}." for e in ENTRIES]
    lines.append("All three continue through every later phase.")
    for phase in PHASES:
        lines.append("")
        lines.append(f"Phase {phase.number}: {phase.title}")
        for step in phase.steps:
            notes = [", ".join(step.requirements)] if step.requirements else ["no requirement"]
            if step.optional:
                notes.append("optional")
            if step.out_of_scope:
                notes.append("out of scope for now: say so, and do not offer to do it")
            lines.append(f"- [{step.id}] {step.text} ({'; '.join(notes)})")
    return "\n".join(lines)
