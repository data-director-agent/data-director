"""The Blueprint's six phases and their steps (§8.2, Figures 1 to 6), as data.

Each step names the functional requirements (§7.1) the Blueprint applies at that point, or none.
A step's `id` is this repository's label, not the Blueprint's. `dd_sdk.process_flow` joins the
steps to the entry points, the agents that serve them and their states.

Writing and reviewing a Data Management Plan are served by alpha agents. Updating it after
publication has no agent yet, so its step is a gap like any other. A step a deployment keeps in
the flow but does not do is marked `out_of_scope`: the phase tracker and the orchestrators name
it and say so, no agent may serve it, and no orchestrator offers to do it. No step is marked now.
TODO(#284): a read-only check of a deposit against an existing Data Management Plan.

Each phase and step also carries wording for researchers, which the app shows: a phase's `name`
and `summary`, a step's `label`, and a step's `prompt`, a first-person opening for a conversation
about it that the app offers to edit and send.

The steps are taken from the figure captions in §8.2, with two boxes the captions leave out:
Figure 2's check of ethical, legal and institutional constraints, and Figure 4's finalising of
controlled vocabularies and ontologies. Figure 1's selection of controlled vocabularies and
ontologies (R3) is moved to that Phase 4 step, `preparation.vocabularies`: a Data Management Plan
does not need it, and the repository chosen in Phase 3 decides which vocabularies apply. Some steps
are ours and in no figure: `setup.project`, describing the project and the data it will produce,
which every later Phase 1 step plans from; `setup.requirements`, finding out what the funder and
institution require before the plan is written; `setup.storage`, planning where data are stored and
backed up while the project runs; `setup.formats`, choosing open formats before collection; and
`deposit.fairness`, a FAIR check of the draft before submission.
TODO(#245):
check the rest against Figures 1 to 6 themselves, which may show other steps or decisions the
captions leave out.

A step's `id` is stored: a researcher's `step_marked` names it in the project log, which outlives
any release. So an id is never deleted or reused. A step taken out of the flow is retired in
`RETIRED_STEPS`, with the step that replaces it where one does, and readers of the log resolve a
stored id through `dd_sdk.process_flow.current_step` (docs/specs/projects.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


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


PHASES: tuple[Phase, ...] = (
    Phase(
        1,
        "Pre-collection setup",
        (
            # Not in Figure 1: our addition, and first. Each later Phase 1 step plans from what
            # the project is and the data it will produce: the README plan, storage, formats and
            # the Data Management Plan. The Blueprint asks that researchers be engaged at project
            # planning (§13) and that governance be addressed at the data management planning
            # stage (§3). The answers are project facts the researcher confirms, proposed from
            # what they say or a proposal they attach, so this is a step and not part of the
            # intake, which asks only what places a project in the flow
            # (docs/specs/orchestration.md, invariant 20).
            Step(
                "setup.project",
                "Describe the project and the data it will produce",
                label="Describe your project",
                prompt=(
                    "Help me describe my project and the data I expect to collect, so that the "
                    "rest of the plan can build on it."
                ),
            ),
            # Not in Figure 1: our addition, before the plan. What the funder and institution
            # require of a project's data decides what its plan must cover, and how, so it is
            # found out before the plan is written or reviewed: the Blueprint addresses governance
            # at the data management planning stage (§3) and confirms what is permitted before
            # anything else (§5.2). Phase 2's `governance.policies` is still the full check, for a
            # researcher who joins there and once the data exist.
            Step(
                "setup.requirements",
                "Find out what the funder and institution require of the data plan",
                label="Find out what your funder and institution require",
                prompt=(
                    "What do my funder and institution require me to plan for my data, and what "
                    "must my Data Management Plan cover?"
                ),
            ),
            # Figure 1: a decision, then create a plan where none exists (optional) or review
            # and update the one that does. Figure 1 puts it last; here it comes before the
            # documentation, storage and formats steps, which each work out a section of the plan
            # in more detail and are placed into it as project facts once decided (#1534).
            Step(
                "setup.dmp-create",
                "Create a Data Management Plan where none exists",
                optional=True,
                label="Write a Data Management Plan",
                prompt=(
                    "Help me write a Data Management Plan covering how my data will be "
                    "collected, stored, shared and kept."
                ),
            ),
            Step(
                "setup.dmp-review",
                "Review and update the Data Management Plan",
                label="Review and update your Data Management Plan",
                prompt="Help me review my Data Management Plan and keep it up to date.",
            ),
            Step(
                "setup.documentation",
                "Draft the data documentation",
                ("R5",),
                label="Plan how your data will be documented",
                prompt="Help me plan how I will document my data before I start collecting it.",
            ),
            # Not in Figure 1: our addition. Where the data live while the project runs, how they
            # are backed up and who can reach them is the first thing a data service asks, and
            # one of a plan's core requirements (Storage and backup during the project); without
            # it, a researcher who has no plan is never asked.
            Step(
                "setup.storage",
                "Plan storage, backup and security during the project",
                label="Plan where your data will be stored and backed up",
                prompt="Help me plan where to store and back up my data while I work on it.",
            ),
            # Not in Figure 1: our addition. Data saved in an open format from the start need no
            # conversion before deposit; Figure 4's `preparation.formats` checks the files once
            # they exist.
            Step(
                "setup.formats",
                "Choose open formats to collect data in",
                ("R3",),
                label="Choose open file formats for your data",
                prompt="Help me choose open file formats to collect my data in.",
            ),
        ),
        name="Plan your data management",
        summary=(
            "Start from what your project is, the data it will produce and what your funder and "
            "institution require, then plan how your data will be collected, documented, stored, "
            "protected, shared and kept, who looks after them and at what cost, and keep the "
            "plan up to date."
        ),
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
            # Figure 2's box after the sensitive-data branch; the caption leaves it out. A "No" to
            # sensitive data does not skip it (docs/specs/intake-reading.md).
            Step(
                "governance.constraints",
                "Check ethical, legal and institutional constraints",
                label="Check the ethical, legal and institutional rules that apply",
                prompt="What ethical, legal or institutional rules apply to sharing my data?",
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
            # Figure 4's box after the metadata standard; the caption folds it into the next step.
            # Figure 1 also selects vocabularies in Phase 1; that selection is made here instead,
            # once the repository and its metadata standard are known, so it carries R3.
            Step(
                "preparation.vocabularies",
                "Finalise controlled vocabularies and ontologies",
                ("R3",),
                label="Choose the standard terms to describe your data",
                prompt=(
                    "Help me choose the standard terms and vocabularies to describe my data, to "
                    "suit my repository and metadata standard."
                ),
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
            # Not in Figure 5: our addition, so that FAIR feedback on the draft comes while the
            # researcher can still act on it. Figure 6's check of the published object stays in
            # Phase 6 (`post.fairness`). It is advice, never a gate: `deposit.validate` decides
            # completeness and the deposit check decides whether a package may be built.
            Step(
                "deposit.fairness",
                "Check how FAIR the draft metadata record is before submitting",
                optional=True,
                label="Check how FAIR your description is before you submit",
                prompt="Help me check how FAIR my dataset's description is before I submit it.",
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
                label="Re-check how FAIR your published record is",
                prompt="Help me check how FAIR the record of my published data is.",
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

# The step ids an earlier release had and this one does not, each with the step that replaces it,
# or None where none does, so that a project log naming one still reads. Never remove an entry.
RETIRED_STEPS: Mapping[str, str | None] = {
    # Figure 1's selection of vocabularies, moved to Phase 4 (#1512). Starting a list before
    # collection is not choosing the terms for a repository, so a mark of it is not carried over.
    "setup.vocabularies": None,
}
