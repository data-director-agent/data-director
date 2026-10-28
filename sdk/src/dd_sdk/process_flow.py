"""The Blueprint's process flow: three entry points into six phases (§8.1, §8.2, Figures 1 to 6).

Researchers do not always start at the beginning. Entry 1 is before data collection, Entry 2 is
with data collected and being prepared for sharing, and Entry 3 is ready to deposit. Each enters
at its own phase and continues through the same final phases. Each step names the functional
requirements (§7.1) the Blueprint applies at that point, or none.

This is Blueprint data, the same for every agent. Which agent serves a requirement is the agent's
own declaration, `AgentSpec.serves`, carried on its manifest entry (ADR-0028); `plan` joins the
two, so an orchestrator keeps no map of agents. Governance as the entry point is deferred to the
Blueprint's v2.0 (Appendix G, comment 1) and is not here.

Creating, reviewing and updating a Data Management Plan are out of scope for the initial phase, so
the figures' steps for them are left out; neither the orchestrator nor the phase tracker offers them.

The steps are taken from the figure captions in §8.2. TODO(#245): check them against Figures 1 to 6
themselves, which are images and may show steps or decisions the captions leave out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Step:
    text: str
    # The Blueprint requirements applied at this step; empty when the figure names none.
    requirements: tuple[str, ...] = ()
    optional: bool = False


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Entry:
    number: int
    text: str
    starts_at: int  # the phase the researcher joins at


PHASES: tuple[Phase, ...] = (
    Phase(
        1,
        "Pre-collection setup",
        (
            Step("Draft the data documentation", ("R5",)),
            Step("Select controlled vocabularies and ontologies", ("R3",)),
        ),
    ),
    Phase(
        2,
        "Governance and constraints",
        (
            Step("Check funder, journal and institutional data sharing policies"),
            Step("Identify and handle sensitive data"),
            Step("Confirm whether an embargo is required"),
            Step("Verify data sharing commitments against the Data Management Plan", ("R8",)),
        ),
    ),
    Phase(
        3,
        "Repository selection",
        (
            Step("Check whether the funder, journal or institution mandates a repository"),
            Step("Recommend a repository where none is mandated", ("R1",)),
            Step("Confirm or arrange persistent identifier (PID) assignment", ("R7",)),
            Step("Check access options and deposit costs"),
            Step("Verify repository certification", optional=True),
        ),
    ),
    Phase(
        4,
        "Data preparation and metadata creation",
        (
            Step("Clean and version the data files"),
            Step("Recommend open formats", ("R3",)),
            Step("Create or review data documentation: READMEs and data dictionaries", ("R5",)),
            Step("Identify the appropriate metadata standard"),
            Step(
                "Complete metadata fields with FAIR-aligned, discipline-appropriate vocabularies "
                "and ontologies",
                ("R2", "R6"),
            ),
        ),
    ),
    Phase(
        5,
        "Deposit and submit",
        (
            Step("Validate metadata quality", ("R4",)),
            Step("Assign a licence"),
            Step(
                "Link to related research outputs: publication DOIs, ORCID, ROR and grant IDs",
                ("R7",),
            ),
            Step("Set access restrictions"),
            Step("Generate a private peer review link", optional=True),
            Step("Upload the files"),
            Step("Review and finalise the submission"),
        ),
    ),
    Phase(
        6,
        "Post-publication",
        (
            Step("Record the deposit in institutional systems where required"),
            Step("Monitor access, downloads and citations"),
            Step("Check embargo release"),
            Step(
                "Evaluate the FAIRness of the published objects and discover related datasets",
                ("R12",),
            ),
            Step("Retrofit FAIR-aligned metadata for existing datasets", ("R9",)),
            Step("Link datasets to related research outputs", ("R11",)),
        ),
    ),
)

ENTRIES: tuple[Entry, ...] = (
    Entry(1, "starting a new project, before data collection begins", 1),
    Entry(2, "data already collected, being prepared for sharing", 2),
    Entry(3, "ready to deposit data into a repository", 3),
)

# The functional requirements of §7.1, which `AgentSpec.serves` may name.
REQUIREMENTS: frozenset[str] = frozenset(f"R{n}" for n in range(1, 13))


def entry(number: int) -> Entry:
    for e in ENTRIES:
        if e.number == number:
            return e
    raise KeyError(f"the Blueprint has no entry point {number}")


def phases_from(start: Entry) -> tuple[Phase, ...]:
    """The phases a researcher entering at `start` goes through, in order."""
    return tuple(p for p in PHASES if p.number >= start.starts_at)


@dataclass(frozen=True)
class PlannedStep:
    phase: Phase
    step: Step
    agent_ids: tuple[str, ...]  # the agents serving any of the step's requirements


def plan(start: Entry, manifest: Iterable[Mapping[str, Any]]) -> list[PlannedStep]:
    """Each step from `start`, with the agents whose manifest entry `serves` its requirements."""
    serving: dict[str, list[str]] = {}
    for agent in sorted(manifest, key=lambda a: str(a.get("agent_id"))):
        for requirement in agent.get("serves") or ():
            serving.setdefault(str(requirement), []).append(str(agent.get("agent_id")))
    return [
        PlannedStep(
            phase,
            step,
            tuple(dict.fromkeys(a for r in step.requirements for a in serving.get(r, ()))),
        )
        for phase in phases_from(start)
        for step in phase.steps
    ]


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
            lines.append(f"- {step.text} ({'; '.join(notes)})")
    return "\n".join(lines)
