# UX flows: asking a data steward for help, and stewards stepping in

*Settled by the [Data stewards](../specs/stewardship.md) spec, which decides where this document and the spec once differed. Written under umbrella issue #370. Flows E to H were added when the spec was written. How each screen looks is still for its build issue.*

## Purpose and status

The Data Director supports data stewards; it does not replace them (Blueprint §3.3), and it exists partly because their help is scarce (the Support Gap, §3.1.1). When it cannot or must not go on, it hands over to a person. Today a `referred` run ends at a dead end and a steward has no way to see a researcher's project; the spec says what is to change. This document describes the experience for three people:

- the **researcher**, who wants help or is told the system cannot give it;
- the **agent** (in practice the orchestrator, or an agent's `referred` or `abstained` outcome), which can offer to flag a question;
- the **data steward**, who receives matters and may step into a project.

It follows the issues under #370: roles (#154), the escalation record (#373), steward actions (#374), the researcher's side (#375), the steward's workspace (#376), notifications (#378), the overviews (#232, #1307), deposit readiness (#1306) and team working (#1308). What remains undecided is marked as a to-do naming the issue that will settle it, following AGENTS.md. Stewards' own documentation is the [Data Steward's Guide](../guide/steward-guide/index.md).

## Design principles

These apply [`best-practices.md`](best-practices.md) to this feature.

1. **Refer and abstain are real screens.** Each has a clear reason, a clear next step and an easy handover to a person.
2. **The agent offers; the researcher agrees.** An agent may suggest asking a steward, but nothing is sent until the researcher says yes, having seen what will be shared.
3. **A person is always shown as a person.** A steward's messages and actions are never presented as an agent's.
4. **Stewards see only what policy lets them, and the researcher can see who looked.** Visibility is scoped, policy-controlled and audited (C1, C2, C14), never "everything by default".
5. **The shell holds no policy.** What a steward may do is what the harness says is permitted; the shell renders it ([App spec](../specs/app.md)).
6. **Nobody has to watch a queue.** Notifications carry a link and a short subject, never research content (#378, #156).
7. **Accessible by keyboard and screen reader.** New states are announced; every hand-over and steward action works without a mouse (#74).

## Vocabulary

| Term | Meaning in this document |
|---|---|
| Data steward | The Blueprint's *data support professional*: data stewards, librarians and others who support researchers with their data (§2). This document uses "steward" for short. |
| Escalation | A record in a project's log that hands a matter to a steward team ([Data stewards](../specs/stewardship.md), invariant 4). |
| Mandatory review | A review the Blueprint requires before a step may proceed. The researcher cannot decline it; see Flow B. |
| Steward's view | The project as a steward sees it: the researcher's own project view, plainly marked, with the escalation beside it. |
| Pause | A steward's hold on a project so no further consequential step runs until lifted (P4, human-on-the-loop). |
| In the loop, on the loop | P4's two kinds of oversight. *In the loop*: a person must approve before the step proceeds. *On the loop*: steps proceed while a person monitors and can intervene. |

The Blueprint gives data support professionals a wider role than this document covers. They are secondary users who may also configure, deploy and run the tool (§2), and §4.1 lists uses for them alone, such as monitoring compliance and managing data access, as well as an overview of data practices within a research community. This document covers their part in escalation and in a project (Flows A to E and H), their overviews (Flow F) and how a team shares the work (Flow G). Owning the policy profile is described in the [steward's guide](../guide/steward-guide/policy-and-profile.md).

### Escalation states

The states ([Data stewards](../specs/stewardship.md), invariant 4) are `open`, `taken`, `waiting for researcher`, `resolved`, `handed back` and `withdrawn`. An escalation moves between them as follows; any move not listed is not allowed.

| From | To | When |
|---|---|---|
| (new) | `open` | The researcher sends it (Flow A) or confirms an agent's offer (Flow B). |
| `open` | `taken` | A steward takes it. |
| `open` | `open` | No steward takes it within the time the profile sets (`stewardship.reroute_after`); it is sent to the same team again and the researcher is told ([Data stewards](../specs/stewardship.md), invariant 13). Moving it to another team is TODO(#1308). |
| `taken` | `open` | The steward releases it without resolving it, so a colleague can take it. |
| `taken` | `waiting for researcher` | The steward asks the researcher something. |
| `waiting for researcher` | `taken` | The researcher replies. |
| `taken`, `waiting for researcher` | `resolved` | The steward resolves it, with a note. |
| `taken`, `waiting for researcher` | `handed back` | The steward hands it back, with a note. |
| `open`, `taken`, `waiting for researcher` | `withdrawn` | The researcher withdraws it. |
| `resolved`, `handed back` | `open` | The researcher re-opens it, with a note. Re-opening keeps the history. |

`withdrawn` is final. The researcher's status line (see "What the researcher sees") follows the current state, so it stops saying "Waiting for you to reply" as soon as the researcher replies.

## Flow A: the researcher asks for a steward

The researcher can ask at any point in a project, not only after something goes wrong.

1. **Entry point.** A persistent, labelled control in the project, "Ask a data steward", reachable by keyboard from every project page.
2. **Compose.** A short note box (what do you need help with?) and a summary of what will be shared: the project's title, its recent conversation and runs, and the matter in question. The summary says plainly that, while the escalation is open, the steward team can open the whole project, and that every look is recorded and shown to the researcher. What the researcher saw is recorded with the escalation ([Data stewards](../specs/stewardship.md), invariants 3 and 4).
3. **Confirm.** "Send to a data steward". The researcher is told who will receive it in general terms (the steward team, or the team the profile routes it to) and roughly what happens next. It goes to the project's support team, the team its owners chose; with none chosen, to the deployment's only team, or, where the profile names several, to the team the researcher picks here, which an owner's pick also makes the project's support team ([Data stewards](../specs/stewardship.md), invariant 4).
4. **Waiting.** The project shows an open escalation in a visible but unobtrusive place (the side bar and a marker in the conversation): its state, its age, the note sent and an **expected response time**. The profile sets the expected time, as text the researcher reads; if nobody has taken it within the profile's `reroute_after`, it is sent to the team again and the status line says so ("Sent again on …"). The researcher can carry on working, and the agents' help stays available while the escalation waits, so the researcher is never blocked on a steward for anything an agent can do. The researcher can also **withdraw** it. Withdrawing does not lift a pause the steward has applied, and a steward's run already in progress finishes and is recorded. The steward's team keeps access to the project until the pause is lifted, so it is never locked out of its own hold; the researcher sees that the pause remains and who can lift it ([Data stewards](../specs/stewardship.md), invariant 8).
5. **Reply.** The steward's reply appears inside the project's conversation, marked plainly as from a named person ("Steward: Name"), and the researcher is notified (Flow D). The researcher can reply in the same place, which moves the escalation back to `taken`.
6. **Close.** The steward resolves or hands back with a note. The researcher sees the outcome and can say they disagree or re-open it (see "Escalation states"). Re-opening keeps the escalation's history.

Empty and failure states: if the profile names no steward route, the control says so instead of failing silently, and points to the institution's usual contact if the profile supplies one. If a steward does not take the escalation within the time the profile sets, it is sent to the team again and the researcher is told (Flow D).

Stewards are scarce. The Blueprint's premise is that skilled support is limited, uneven and often unavailable at short notice (§3.1.1), so these flows must not recreate the bottleneck the tool is meant to relieve. Besides the expected response time and the agents' continued help, §13.2 suggests a first-pass review by another AI agent before human review, to manage volume. Whether an escalation gets such a first pass, and how its result is shown to the steward and the researcher, is a spike, TODO(#1310).

## Flow B: the agent offers to flag a question

There are three triggers, one pattern: **explain, offer, confirm.**

| Trigger | Example | What the researcher sees | Loop (P4) |
|---|---|---|---|
| A `referred` outcome from the policy gate | A run needs approval the profile reserves for a steward | A card in the conversation: why the run stopped, and "Send this to a data steward" | In the loop: the step waits for a person (see "Mandatory review") |
| An agent abstains or cannot help | No source supports an answer | The abstain card, with the reason, then an offer to ask a steward | In the loop: the researcher decides whether to escalate |
| The orchestrator suggests it | The researcher's questions keep returning to something no agent covers | A message in the orchestrator's voice suggesting a steward, with a button | In the loop: the researcher decides whether to escalate |

The "Loop (P4)" column is the classification P4 asks to be documented per workflow.

The pattern:

1. **Explain.** The agent states, truthfully, what it could not do and why. It never implies it answered when it did not ([orchestrator prompt](../../agents/orchestrator-model/src/dd_agent_orchestrator_model/system_prompt.md): report abstentions and refusals faithfully).
2. **Offer.** One clear option: "Ask a data steward about this". The offer is a suggestion; the agent does not decide on the researcher's behalf.
3. **Show what will be shared.** The same summary as Flow A, prefilled with the question the agent drafted, which the researcher can edit.
4. **Researcher confirms.** Only then is the escalation created, recorded against the project with its origin (policy gate, agent, orchestrator) so a steward knows why it arrived.
5. **Decline is easy, except for a mandatory review.** "Not now" dismisses the offer, and it does not nag. Proposed default: once declined, the agent does not raise the offer again for the same trigger in that conversation; a different trigger, or a new run that ends in the same way, may offer again. The researcher can still ask at any time through Flow A. Decided in #375: the orchestrator's prompt does not offer again for the same matter in that conversation after "Not now"; the offer beside a run stays with that run.

Two cases differ slightly:

- **Mandatory review.** The step is stopped and cannot proceed until the responsible person has reviewed it. The card says so, and the review is the next step rather than an optional extra. There is no "Not now". Where the reviewer is a steward, the card offers "Send to a data steward" and "Leave it stopped"; where the reviewer is the researcher, it offers the review itself and "Leave it stopped". A stopped step stays in the project's list of runs with its card and its action, so the researcher can come back to it later and is never left at a dead end. A policy referral is one case of this class. Whether the reviewer's approval then resumes the run is undecided, TODO(#16).
- **A discrepancy flagged for human review** (for example R8): the offer names the discrepancy, so the researcher can see what the steward would look at. This is an ordinary offer, not a mandatory review: §5.1 says a DMP discrepancy triggers review rather than blocking.

### Mandatory review

The Blueprint makes human review compulsory in several places. Each trigger below stops the step until the named person has reviewed it; where that person is a steward, "Not now" cannot bypass the review. The reviewer column gives the defaults; the deployment's profile sets the reviewer of each, from its governance agreement (§5.1) ([Data stewards](../specs/stewardship.md), invariant 9), TODO(#73).

| Trigger | Blueprint | Proposed reviewer | What stays stopped |
|---|---|---|---|
| The policy gate refers a run | §5.1, §5.4 (override rights are role-based) | Steward, or the role the profile names | The referred run |
| A policy conflict the tool can surface but not resolve, such as funder and journal requirements that disagree | §5.1, R1 | Steward | Repository selection and anything that depends on it |
| Personal identifiers or sensitive information flagged or detected | C2, §5.4 | Researcher, who is directed to an external anonymisation or deidentification workflow; a steward as well where the profile requires | The sharing workflow |
| Generic, uncurated or low-quality metadata before submission | C15, §5.4 | Researcher, who approves the record (R2); a steward as well where the profile requires | Submission |
| Ethics approval or embargo status not yet confirmed | §5.2, C2 | The responsible person: the researcher, or the ethics or governance contact the profile names | Any sharing or deposit workflow |

All five are in the loop (P4): a person must act before the step proceeds.

## Flow C: the steward's workspace

### The queue

A single place listing escalations routed to the signed-in steward:

- columns: project, researcher, reason (and origin), age, state, who has taken it;
- filters by state; sort by age by default;
- **Take** an escalation, so colleagues see who has it and do not duplicate work;
- keyboard-operable table with clear row focus and announced state changes.

### The project overview (read-only, #232)

Built: the **Projects** page beside the queue (`/steward/projects`, from `GET /api/steward/projects`).

Beside the queue, a list of projects the steward may see, with owner, current phase, recent runs and outcomes (including abstentions and referrals), and anything awaiting human review. Which projects appear is decided by the harness from the profile.

By default a steward sees only a project with an escalation routed to their team, because the overview discloses a person's work (C2, P4). Under that default the overview lists the same projects as the queue, adding the project details beside each escalation. It is a separate view only where the profile sets `stewardship.visibility: scope`, and then lists the projects whose owners chose the team as their support team ([Data stewards](../specs/stewardship.md), invariant 3).

A less intrusive alternative to a per-project overview is the aggregate one in §4.1: an "overview of data practices within a research community", such as the metadata standards and repositories most used, without showing any one person's work. Stewards get it as well as the per-project list, not instead of it (Flow F, TODO(#1307)).

Showing the overview is itself a read. Each project listed is recorded as viewed by that steward (#374), and appears in the researcher's list of who has looked, in the same way as opening the project.

### Opening a project as a steward

1. Opening a project shows the **same project view the researcher has**, so the steward sees what the researcher sees.
2. A persistent banner reads "Viewing as a data steward", with the researcher's name and the escalation, and cannot be dismissed.
3. The escalation sits beside the project: the researcher's note, its origin, the history and the steward's own notes.
4. Opening is recorded. The researcher can see "Steward Name viewed this project on date".

### What a steward can do

The closed list in [Data stewards](../specs/stewardship.md), invariant 6. The shell shows only the actions the harness reports as permitted, each with its own explanation. A refused action is explained, not hidden.

| Action | Experience | Loop (P4) |
|---|---|---|
| Read the project | Default on opening. | Neither: no step proceeds |
| Write to the researcher | Reply in the conversation, marked as a person. | Neither: no step proceeds |
| Clear a gated action | Approve or refuse a step the policy gate referred to a steward (a §5.1 policy exception), with a reason required. Clearing the gate does not approve the content; see "Who approves what". | In the loop |
| Propose an edit to the researcher's documents | The existing document-version flow ([Projects](../specs/projects.md), #196): the steward's edit becomes a proposed version, marked as theirs, which the researcher accepts or rejects. | In the loop (the researcher decides) |
| Run an agent in the project | The same run controls, labelled as run by the steward. The run acts for the steward, with the project as context, and its drafts are proposed versions the researcher decides. | In the loop for any consequential step, as for the researcher's own runs |
| Pause the project | A single labelled control; the researcher sees the project is paused, by whom and why. Lifting it is as prominent as applying it. The steward's team keeps access until it is lifted, even if the researcher withdraws the escalation (Flow A, step 4). | On the loop: the steward monitors and intervenes |
| Note on a deposit item; co-approve a deposit | See Flow E. | In the loop where the profile requires co-approval |
| Resolve or hand back | A note to the researcher is required; the state change is announced. | Neither: closes the escalation |

The "Loop (P4)" column is the classification P4 asks to be documented per workflow.

Every action is checked by policy and recorded (#374). Where a steward changes a result, the researcher sees what changed and by whom, and can disagree (see Flow A, step 6). A steward's contributions are recorded with a CRediT role (for example *Data curation*) and identified by ORCID where the steward has one, not only as a "decider" (P5). *Data curation* applies to an edit, a run or a note, and *Validation* to clearing a gate, a review or a co-approval ([Data stewards](../specs/stewardship.md), invariant 12).

### Who approves what

The Blueprint keeps two kinds of approval apart: the researcher approves their own outputs (R2; §8, "the researcher is responsible for the final data submission"), while an accountable institutional role resolves policy exceptions (§5.1). A steward **clears the gated action**, and the researcher still **approves the content** and the deposit. A steward never decides on a researcher's documents. A profile may add a steward's co-approval before deposit, but never removes the researcher's (Flow E; [Data stewards](../specs/stewardship.md), invariant 7). A steward's edits, runs and decisions act for the steward and are recorded as theirs.

## Flow D: notifications (#378)

The deployment holds no person's email address ([Policy and identity](../specs/policy-and-identity.md), invariant 15), so the team is emailed at its own address, and the researcher is told in the app ([Data stewards](../specs/stewardship.md), invariant 13).

- **Steward team:** emailed at the address the profile names for the team when an escalation is routed to it, when one nobody took is sent again, and when the researcher replies, withdraws or re-opens one (re-opening is how a researcher disagrees with an outcome), so nobody has to watch the queue to find out. The address may be a shared mailbox, or a helpdesk's intake address, which makes each message a ticket there; the harness record stays authoritative. A team with no address is told nothing by email and reads **Requests**.
- **Researcher:** **Updates** in the banner counts what stewards did that they have not seen: a question, a message, a resolution, a hand-back, or a request sent again. Opening it lists each with a link to the project and marks them seen; a new one is announced in the polite live region.
- **Content:** a link and a short subject only, never research content or personal data beyond what is needed.
- **Choice:** a team chooses in the profile which of its events it is emailed about (`notify_on`). A researcher chooses on the Settings page, under Notifications, which kinds of update the banner shows; the choice is kept in their browser.

## Flow E: getting a project ready to deposit (#1306)

Stewards often help most just before deposit, when the Blueprint's mandatory reviews fall due (C2, C15, R8). A steward with access to the project works through its deposit tab beside the researcher.

1. **The same tab, read-only.** Under the banner, the steward sees what the researcher sees on the deposit tab: the validation report, each item the check flagged before packaging, the three confirmations (ethics approval, data protection advice, third-party rights) and the package, if built. The steward cannot decide an item or make a confirmation; those are the researcher's ([Deposit](../specs/deposit.md)).
2. **Notes against items.** The steward can add a note to a flagged item or a failed validation rule ("this field note names a participant's village"). The note appears beside the item for the researcher, marked with the steward's name, and is recorded.
3. **Proposed fixes.** Where the fix is in a document, the steward proposes an edit (Flow C) and the note links to it.
4. **Co-approval, where the profile requires it.** With `stewardship.deposit_co_approval` on, once the researcher has approved the package the deposit tab shows "Waiting for a data steward to co-approve", and the steward sees **Co-approve** with the package's digest and a required reason, and **Ask for changes**, which writes to the researcher. A new package needs a new co-approval. The researcher's approval is never replaced: co-approval adds a check (§5.1) and the researcher still deposits.
5. **A steward who is a member of the project** cannot co-approve it (Flow G).

| Step | Loop (P4) |
|---|---|
| Notes and proposed fixes | Neither: the researcher decides |
| Co-approval | In the loop: the deposit waits for it |

## Flow F: the steward's overviews (#232, #1307)

A steward has up to three views beyond the queue, each from the harness and none showing more than policy allows:

- **The team's projects** (#232), only where the profile sets `visibility: scope`: projects whose owners chose the team as their support team, with phase, recent outcomes and anything awaiting a review. Listing a project is a read and is recorded, as opening it is.
- **The community overview** (#1307, §4.1): counts across the team's scope, such as the repositories and metadata standards chosen, referrals and abstentions by reason, and escalation volume, age and time to resolution. It names no project or person, and suppresses small counts. Viewing it records nothing on any project because it reads none.
- **Compliance signals** (#1307, §4.1 "monitor compliance"): how many projects are stopped at each mandatory review, so the team sees where researchers get stuck without opening their work.

## Flow G: working as a team (#1308)

Stewards are scarce and are sometimes away (§3.1.1), so escalations belong to a team, not to one person.

- **Release** hands an escalation back to the team's queue, with an optional note. **Reassign** gives it to a named colleague in the same team. **Transfer** moves it to another team, with a required note, and the researcher sees the new team's name.
- **Cover.** Any member of a team can lift a pause another member applied, so a hold never outlives a steward's availability.
- **Conflict of interest.** A steward who is a member or owner of a project acts there only as a member: they cannot take its escalation, clear its gates, pause it or co-approve its deposit. The queue shows such an escalation without the **Take** action, with the reason.
- Each move appears in the project's log for the researcher.

## Flow H: pause and resume (#374)

**The steward.** **Pause project** opens a dialogue with a required reason, which the researcher will see, and a reminder of what a pause stops: every step that is not advice, and the deposit. The project then shows "Paused by you" with **Lift pause** beside it.

**The researcher.** The project's status line reads:

> Paused by Name (Library Research Data Team) on 14 November: "Please wait while we check the consent forms." Advice and conversation still work. Only the data stewards can lift this pause.

A step the pause stops ends with a card naming the pause and its reason, never a bare failure; the researcher can write to the steward from it. When the pause is lifted, the status line says so and by whom, and the stopped steps can be started again. A pause never lifts itself.

## What the researcher sees, in one place

On a project with an escalation, a single status line answers "what is happening with my request?". It follows the escalation's state; for example, while the steward is waiting on the researcher:

> Sent to the data stewards on 12 November · Taken by Name · Waiting for you to reply

The project also lists who has viewed it as a steward, and any steward actions, in the project's log (the project log already records decisions and membership events, [Projects](../specs/projects.md)).

## Open questions

The rest is decided in the spec. Each question below is owned by the issue shown.

| Question | Owner |
|---|---|
| Mapping identity-provider group claims to steward teams | #936 |
| For a project that spans several institutions, whose steward team receives it (§5.1 asks for an inter-institutional agreement) | #371 |
| Whether an escalation gets a first-pass AI review before a steward sees it (§13.2) | #1310 |
| What happens to a project whose owners have all left | #1309 |
| Whether these defaults (escalation-only visibility, a pause that never lapses) hold up with working teams and the RDA working group (Blueprint §13.1 names escalation and suspension the key community governance question) | #371 |

## Suggested next steps

1. Use the discovery task (#371) to test these flows with real RDM teams: how do they receive and handle requests today?
2. Turn each flow into screens: the researcher's request and agent offer (#375) first, then the steward's workspace (#376).
3. Treat escalation records as evidence. Why agents abstain or refer, and how stewards resolve those cases, feeds the Measurability constraint (C16) and the Blueprint's evaluation (§10), and shows whether the tool is eroding in-house expertise (§5.5). Pause and its use are also implementation evidence to take back to the RDA working group on §13.1.
