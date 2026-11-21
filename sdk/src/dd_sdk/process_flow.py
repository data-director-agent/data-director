"""The Blueprint's process flow: three entry points into six phases (§8.1, §8.2, Figures 1 to 6).

Researchers do not always start at the beginning. Entry 1 is before data collection, Entry 2 is
with data collected and being prepared for sharing, and Entry 3 is ready to deposit. Each enters
at its own phase and continues through the same final phases. Each step names the functional
requirements (§7.1) the Blueprint applies at that point, or none.

This is Blueprint data, the same for every agent. Which steps an agent serves is the agent's own
declaration, `AgentSpec.serves`, carried on its manifest entry (docs/specs/orchestration.md); `plan`
joins the two, so an orchestrator keeps no map of agents. An agent names steps, not requirements:
the requirements it bears on follow from its steps' `requirements`. A step's `id` is this
repository's label, not the Blueprint's. Governance as the entry point is deferred to the
Blueprint's v2.0 (Appendix G, comment 1) and is not here.

Creating, reviewing and updating a Data Management Plan are out of scope for the initial phase.
The figures' steps for them are kept so that the flow is complete, and marked `out_of_scope`: the
phase tracker and the orchestrators name them and say so, no agent may serve them, and no
orchestrator offers to do them. TODO(#284): a read-only check of a deposit against an existing
Data Management Plan.

Where a researcher is in the flow is never stored: the harness derives each step's state (open,
started, done or skipped) from the project log on every turn, and `progress` joins those states
to the plan. Work is not linear, so a step done out of order counts wherever it falls, and the
next step `suggested_next` names is a suggestion an orchestrator offers, never a gate
(docs/specs/orchestration.md).

Each phase and step also carries wording for researchers, which the app shows: a phase's `name`
and `summary`, a step's `label`, and a step's `prompt`, a first-person opening for a conversation
about it that the app offers to edit and send.

The steps are taken from the figure captions in §8.2. TODO(#245): check them against Figures 1 to 6
themselves, which are images and may show steps or decisions the captions leave out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Step:
    # A stable label, `<phase>.<step>`, that `AgentSpec.serves` may name
    # (docs/specs/orchestration.md).
    id: str
    text: str
    # The Blueprint requirements applied at this step; empty when the figure names none.
    requirements: tuple[str, ...] = ()
    optional: bool = False
    # The Blueprint has the step but this project does not yet do it. It stays in the flow so the
    # flow is complete; no agent may serve it (`AgentSpec`) and an orchestrator says it is out of
    # scope rather than "no agent yet".
    out_of_scope: bool = False
    # A person decides the step and no agent may serve it (C2): an agent may flag what bears on
    # it, and stops there. The app shows it as never delegated (docs/specs/agents.md).
    person_decides: bool = False
    # What the step is, in a researcher's words, for the people using the app. `text` is the
    # Blueprint's wording, which the orchestrator reasons over.
    label: str = ""
    # How a researcher might open a conversation about the step, in their own words, offered in the
    # app as a message to edit and send. It names no requirement and no agent.
    prompt: str = ""


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    steps: tuple[Step, ...]
    # The phase in a researcher's words: a short name and one sentence on what it is for. `title`
    # is the Blueprint's.
    name: str = ""
    summary: str = ""


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
            Step(
                "setup.documentation",
                "Draft the data documentation",
                ("R5",),
                label="Plan how your data will be documented",
                prompt="Help me plan how I will document my data before I start collecting it.",
            ),
            Step(
                "setup.vocabularies",
                "Select controlled vocabularies and ontologies",
                ("R3",),
                label="Choose standard terms to describe your data",
                prompt="Help me choose standard terms and vocabularies to describe my data.",
            ),
            # Figure 1: a decision, then create a plan where none exists (optional) or review
            # and update the one that does.
            Step(
                "setup.dmp-create",
                "Create a Data Management Plan where none exists",
                optional=True,
                out_of_scope=True,
                label="Write a Data Management Plan",
                prompt="Help me write a Data Management Plan for my project.",
            ),
            Step(
                "setup.dmp-review",
                "Review and update the Data Management Plan",
                out_of_scope=True,
                label="Review your Data Management Plan",
                prompt="Help me review my Data Management Plan.",
            ),
        ),
        name="Plan ahead",
        summary="Before you collect any data: decide how it will be described.",
    ),
    Phase(
        2,
        "Governance and constraints",
        (
            Step(
                "governance.policies",
                "Check funder, journal and institutional data sharing policies",
                label="Check what your funder, journal and institution expect",
                prompt="What do my funder, journal and institution expect me to do with my data?",
            ),
            # Figure 2 has one step, "identifying and handling sensitive data". It is split here so
            # that an agent can flag sensitive data without deciding how it is treated
            # (docs/specs/orchestration.md).
            Step(
                "governance.sensitive-data-identify",
                "Identify sensitive data",
                label="Spot any sensitive information in your data",
                prompt="Help me find out whether my data hold any sensitive information.",
            ),
            Step(
                "governance.sensitive-data-handle",
                "Handle sensitive data",
                person_decides=True,
                label="Decide how sensitive data will be protected",
                prompt="Help me decide how to protect the sensitive information in my data.",
            ),
            Step(
                "governance.embargo",
                "Confirm whether an embargo is required",
                label="Decide whether to delay public release",
                prompt="Help me decide whether I should delay the public release of my data.",
            ),
            Step(
                "governance.dmp",
                "Verify data sharing commitments against the Data Management Plan",
                ("R8",),
                label="Check your plans match your Data Management Plan",
                prompt="Help me check that my plans for sharing match my Data Management Plan.",
            ),
        ),
        name="Check the rules",
        summary=(
            "Find out what your funder, journal and institution require, "
            "and how your data must be protected."
        ),
    ),
    Phase(
        3,
        "Repository selection",
        (
            Step(
                "repository.mandated",
                "Check whether the funder, journal or institution mandates a repository",
                label="Find out whether you must use a particular repository",
                prompt="Do I have to deposit my data in a particular repository?",
            ),
            Step(
                "repository.recommend",
                "Recommend a repository where none is mandated",
                ("R1",),
                label="Choose a repository",
                prompt="Help me choose a repository for my data.",
            ),
            Step(
                "repository.pid",
                "Confirm or arrange persistent identifier (PID) assignment",
                ("R7",),
                label="Make sure your data will get a permanent identifier, such as a DOI",
                prompt="How will my data get a permanent identifier, such as a DOI?",
            ),
            Step(
                "repository.access-and-costs",
                "Check access options and deposit costs",
                label="Check who can access the data and what depositing costs",
                prompt=(
                    "Who will be able to access my data in the repository, "
                    "and what will depositing cost?"
                ),
            ),
            Step(
                "repository.certification",
                "Verify repository certification",
                optional=True,
                label="Check that the repository is trustworthy",
                prompt="Help me check that my chosen repository is trustworthy.",
            ),
        ),
        name="Choose where to share",
        summary="Pick a repository that suits your data and meets those requirements.",
    ),
    Phase(
        4,
        "Data preparation and metadata creation",
        (
            Step(
                "preparation.files",
                "Clean and version the data files",
                label="Tidy and version your files",
                prompt="Help me tidy and version my data files.",
            ),
            Step(
                "preparation.formats",
                "Recommend open formats",
                ("R3",),
                label="Save your data in open formats",
                prompt=(
                    "Help me check whether my files are in open formats, "
                    "and what to save them as if not."
                ),
            ),
            Step(
                "preparation.documentation",
                "Create or review data documentation: READMEs and data dictionaries",
                ("R5",),
                label="Write a README and a data dictionary",
                prompt="Help me write a README and a data dictionary for my data.",
            ),
            Step(
                "preparation.metadata-standard",
                "Identify the appropriate metadata standard",
                label="Choose the metadata standard to follow",
                prompt="Which metadata standard should I follow for my data?",
            ),
            Step(
                "preparation.metadata",
                "Complete metadata fields with FAIR-aligned, discipline-appropriate vocabularies "
                "and ontologies",
                ("R2", "R6"),
                label="Fill in the description of your dataset",
                prompt="Help me fill in the description of my dataset.",
            ),
        ),
        name="Get your data ready",
        summary="Tidy the files and describe them so others can understand and reuse them.",
    ),
    Phase(
        5,
        "Deposit and submit",
        (
            Step(
                "deposit.validate",
                "Validate metadata quality",
                ("R4",),
                label="Check the description is complete and correct",
                prompt="Help me check that the description of my dataset is complete and correct.",
            ),
            Step(
                "deposit.licence",
                "Assign a licence",
                label="Choose a licence",
                prompt="Help me choose a licence for my data.",
            ),
            Step(
                "deposit.links",
                "Link to related research outputs: publication DOIs, ORCID, ROR and grant IDs",
                ("R7",),
                label="Link to your paper, your ORCID iD, your institution and your grant",
                prompt=(
                    "Help me link my data to my paper, my ORCID iD, my institution and my grant."
                ),
            ),
            Step(
                "deposit.access",
                "Set access restrictions",
                label="Set who can see or download the data",
                prompt="Help me decide who can see or download my data.",
            ),
            Step(
                "deposit.review-link",
                "Generate a private peer review link",
                optional=True,
                label="Create a private link for peer reviewers",
                prompt="How do I create a private link to my data for peer reviewers?",
            ),
            Step(
                "deposit.upload",
                "Upload the files",
                label="Upload your files",
                prompt="Help me upload my files to the repository.",
            ),
            Step(
                "deposit.finalise",
                "Review and finalise the submission",
                label="Review and submit",
                prompt="Help me review my deposit before I submit it.",
            ),
        ),
        name="Deposit your data",
        summary="Check the description, set the licence and access, and submit.",
    ),
    Phase(
        6,
        "Post-publication",
        (
            Step(
                "post.dmp-update",
                "Update the Data Management Plan to reflect the data published",
                out_of_scope=True,
                label="Update your Data Management Plan with what you published",
                prompt="Help me update my Data Management Plan with what I published.",
            ),
            Step(
                "post.institutional-record",
                "Record the deposit in institutional systems where required",
                label="Record the deposit with your institution",
                prompt="Help me record my deposit with my institution.",
            ),
            Step(
                "post.monitor",
                "Monitor access, downloads and citations",
                label="Follow downloads and citations",
                prompt="How can I follow the downloads and citations of my data?",
            ),
            Step(
                "post.embargo-release",
                "Check embargo release",
                label="Release your data when the delay ends",
                prompt="Help me release my data when the embargo ends.",
            ),
            Step(
                "post.fairness",
                "Evaluate the FAIRness of the published objects and discover related datasets",
                ("R12",),
                label="Check how FAIR your published data are",
                prompt="Help me check how FAIR my published data are.",
            ),
            Step(
                "post.retrofit",
                "Retrofit FAIR-aligned metadata for existing datasets",
                ("R9",),
                label="Improve the description of older datasets",
                prompt="Help me improve the description of an older dataset.",
            ),
            Step(
                "post.links",
                "Link datasets to related research outputs",
                ("R11",),
                label="Connect your data to related publications and datasets",
                prompt="Help me connect my data to related publications and datasets.",
            ),
        ),
        name="After publication",
        summary="Follow how your data are used and keep their records up to date.",
    ),
)

ENTRIES: tuple[Entry, ...] = (
    Entry(1, "starting a new project, before data collection begins", 1),
    Entry(2, "data already collected, being prepared for sharing", 2),
    Entry(3, "ready to deposit data into a repository", 3),
)

# The functional requirements of §7.1.
REQUIREMENTS: frozenset[str] = frozenset(f"R{n}" for n in range(1, 13))

# The steps' ids, which `AgentSpec.serves` names (docs/specs/orchestration.md).
STEPS: frozenset[str] = frozenset(s.id for p in PHASES for s in p.steps)

# The steps the Blueprint has and this project does not yet do; no agent may serve them.
OUT_OF_SCOPE: frozenset[str] = frozenset(s.id for p in PHASES for s in p.steps if s.out_of_scope)

# The steps a person decides (C2); no agent may serve them either.
PERSON_DECIDES: frozenset[str] = frozenset(
    s.id for p in PHASES for s in p.steps if s.person_decides
)


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


# How far a step has gone, as the project log shows it (docs/specs/orchestration.md).
StepState = Literal["open", "started", "done", "skipped"]
STEP_STATES: tuple[StepState, ...] = ("open", "started", "done", "skipped")


@dataclass(frozen=True)
class ProgressStep:
    phase: Phase
    step: Step
    agent_ids: tuple[str, ...]  # the agents serving the step
    state: StepState


def progress(
    start: Entry | None, states: Mapping[str, str], manifest: Iterable[Mapping[str, Any]]
) -> list[ProgressStep]:
    """Each step from `start` with its state and the agents serving it. A phase before `start` is
    included where one of its steps has started, since work done out of order still counts. With
    no `start`, every phase is included. A step `states` leaves out is open."""
    first = start.starts_at if start is not None else 1
    earlier = {p.number for p in PHASES if any(_state(states.get(s.id)) != "open" for s in p.steps)}
    included = {p.number for p in PHASES if p.number >= first} | earlier
    planned = plan(entry(1), manifest)
    return [
        ProgressStep(p.phase, p.step, p.agent_ids, _state(states.get(p.step.id)))
        for p in planned
        if p.phase.number in included
    ]


def _state(value: str | None) -> StepState:
    return next((s for s in STEP_STATES if s == value), "open")


def suggested_next(steps: Iterable[ProgressStep], start: Entry | None) -> ProgressStep | None:
    """The step to suggest next: the first one from `start`'s phase that is neither done nor
    skipped, in scope and not optional; a started step before an open one; and, within the phase
    of the first open step, one an agent serves before one no agent does, so that a researcher is
    not first sent to a step nothing here can help with when the same phase has one it can
    (#1377). The suggestion never leaves that phase for an agent: with none of its steps served,
    as when `steps` were planned from no manifest, it is the first open one, named as having no
    agent. None when all are done.

    With no `start`, where the researcher is is not known, so no open step is suggested: only a
    started one, from any phase, or None. Suggesting the first step of Phase 1 would tell a
    researcher whose data are already collected to plan their collection."""
    first = start.starts_at if start is not None else 1
    candidates = [
        s
        for s in steps
        if s.phase.number >= first
        and s.state in ("open", "started")
        and not s.step.out_of_scope
        and not s.step.optional
    ]
    started = [s for s in candidates if s.state == "started"]
    if start is None:
        return next(iter(started), None)
    phase = candidates[0].phase.number if candidates else None
    served = [s for s in candidates if s.agent_ids and s.phase.number == phase]
    return next(iter(started or served or candidates), None)
