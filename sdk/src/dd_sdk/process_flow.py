"""The Blueprint's process flow: three entry points into six phases (§8.1, §8.2, Figures 1 to 6).

Researchers do not always start at the beginning. Entry 1 is before data collection, Entry 2 is
with data collected and being prepared for sharing, and Entry 3 is ready to deposit. Each enters
at its own phase and continues through the same final phases. Each step names the functional
requirements (§7.1) the Blueprint applies at that point, or none.

This is Blueprint data, the same for every agent. Which steps an agent serves is the agent's own
declaration, `AgentSpec.serves`, carried on its manifest entry (ADR-0028); `plan` joins the two,
so an orchestrator keeps no map of agents. An agent names steps, not requirements: the
requirements it bears on follow from its steps' `requirements`. A step's `id` is this repository's
label, not the Blueprint's. Governance as the entry point is deferred to the
Blueprint's v2.0 (Appendix G, comment 1) and is not here.

Creating, reviewing and updating a Data Management Plan are out of scope for the initial phase, so
the figures' steps for them are left out; neither the orchestrator nor the phase tracker offers
them. TODO(#284): a read-only check of a deposit against an existing Data Management Plan.

The steps are taken from the figure captions in §8.2. TODO(#245): check them against Figures 1 to 6
themselves, which are images and may show steps or decisions the captions leave out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Step:
    # A stable label, `<phase>.<step>`, that `AgentSpec.serves` may name (ADR-0032).
    id: str
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
            Step("setup.documentation", "Draft the data documentation", ("R5",)),
            Step("setup.vocabularies", "Select controlled vocabularies and ontologies", ("R3",)),
        ),
    ),
    Phase(
        2,
        "Governance and constraints",
        (
            Step(
                "governance.policies",
                "Check funder, journal and institutional data sharing policies",
            ),
            # Figure 2 has one step, "identifying and handling sensitive data". It is split here so
            # that an agent can flag sensitive data without deciding how it is treated (ADR-0032).
            Step("governance.sensitive-data-identify", "Identify sensitive data"),
            Step("governance.sensitive-data-handle", "Handle sensitive data"),
            Step("governance.embargo", "Confirm whether an embargo is required"),
            Step(
                "governance.dmp",
                "Verify data sharing commitments against the Data Management Plan",
                ("R8",),
            ),
        ),
    ),
    Phase(
        3,
        "Repository selection",
        (
            Step(
                "repository.mandated",
                "Check whether the funder, journal or institution mandates a repository",
            ),
            Step("repository.recommend", "Recommend a repository where none is mandated", ("R1",)),
            Step(
                "repository.pid",
                "Confirm or arrange persistent identifier (PID) assignment",
                ("R7",),
            ),
            Step("repository.access-and-costs", "Check access options and deposit costs"),
            Step("repository.certification", "Verify repository certification", optional=True),
        ),
    ),
    Phase(
        4,
        "Data preparation and metadata creation",
        (
            Step("preparation.files", "Clean and version the data files"),
            Step("preparation.formats", "Recommend open formats", ("R3",)),
            Step(
                "preparation.documentation",
                "Create or review data documentation: READMEs and data dictionaries",
                ("R5",),
            ),
            Step("preparation.metadata-standard", "Identify the appropriate metadata standard"),
            Step(
                "preparation.metadata",
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
            Step("deposit.validate", "Validate metadata quality", ("R4",)),
            Step("deposit.licence", "Assign a licence"),
            Step(
                "deposit.links",
                "Link to related research outputs: publication DOIs, ORCID, ROR and grant IDs",
                ("R7",),
            ),
            Step("deposit.access", "Set access restrictions"),
            Step("deposit.review-link", "Generate a private peer review link", optional=True),
            Step("deposit.upload", "Upload the files"),
            Step("deposit.finalise", "Review and finalise the submission"),
        ),
    ),
    Phase(
        6,
        "Post-publication",
        (
            Step(
                "post.institutional-record",
                "Record the deposit in institutional systems where required",
            ),
            Step("post.monitor", "Monitor access, downloads and citations"),
            Step("post.embargo-release", "Check embargo release"),
            Step(
                "post.fairness",
                "Evaluate the FAIRness of the published objects and discover related datasets",
                ("R12",),
            ),
            Step("post.retrofit", "Retrofit FAIR-aligned metadata for existing datasets", ("R9",)),
            Step("post.links", "Link datasets to related research outputs", ("R11",)),
        ),
    ),
)

ENTRIES: tuple[Entry, ...] = (
    Entry(1, "starting a new project, before data collection begins", 1),
    Entry(2, "data already collected, being prepared for sharing", 2),
    Entry(3, "ready to deposit data into a repository", 3),
)

# The functional requirements of §7.1.
REQUIREMENTS: frozenset[str] = frozenset(f"R{n}" for n in range(1, 13))

# The steps' ids, which `AgentSpec.serves` names (ADR-0028).
STEPS: frozenset[str] = frozenset(s.id for p in PHASES for s in p.steps)


def requirements_of(step_ids: Iterable[str]) -> tuple[str, ...]:
    """The requirements the steps named apply, in R-number order and without repeats."""
    wanted = set(step_ids)
    found = {r for p in PHASES for s in p.steps if s.id in wanted for r in s.requirements}
    return tuple(sorted(found, key=lambda r: int(r[1:])))


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
    agent_ids: tuple[str, ...]  # the agents serving the step


def plan(start: Entry, manifest: Iterable[Mapping[str, Any]]) -> list[PlannedStep]:
    """Each step from `start`, with the agents whose manifest entry `serves` the step's id."""
    serving: dict[str, list[str]] = {}
    for agent in sorted(manifest, key=lambda a: str(a.get("agent_id"))):
        for served in dict.fromkeys(agent.get("serves") or ()):
            serving.setdefault(str(served), []).append(str(agent.get("agent_id")))
    return [
        PlannedStep(phase, step, tuple(serving.get(step.id, ())))
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
            lines.append(f"- [{step.id}] {step.text} ({'; '.join(notes)})")
    return "\n".join(lines)
