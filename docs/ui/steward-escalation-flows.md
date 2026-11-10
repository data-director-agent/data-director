# UX flows: asking a data steward for help, and stewards stepping in

*Draft for discussion. Written under umbrella issue #370. It is a design input to the spec (#372), not a decision: nothing here is settled until the spec is merged.*

## Purpose and status

The Data Director supports data stewards; it does not replace them (Blueprint §3). When it cannot or must not go on, it hands over to a person. Today a `referred` run ends at a dead end and a steward has no way to see a researcher's project. This document sketches the experience for three people:

- the **researcher**, who wants help or is told the system cannot give it;
- the **agent** (in practice the orchestrator, or an agent's `referred` or `abstained` outcome), which can offer to flag a question;
- the **data steward**, who receives matters and may step into a project.

It follows the issues under #370: the spec (#372), the overview (#232), the researcher's side (#375), the steward's workspace (#376), notifications (#378) and roles (#154). Anything marked **[Open]** is a question those issues leave undecided; the draft shows a *proposed default* so the flow can be read end to end, and says so.

## Design principles

These apply [`best-practices.md`](best-practices.md) to this feature.

1. **Refer and abstain are real screens.** Each has a clear reason, a clear next step and an easy handover to a person.
2. **The agent offers; the researcher agrees.** An agent may suggest asking a steward, but nothing is sent until the researcher says yes, having seen what will be shared.
3. **A person is always shown as a person.** A steward's messages and actions are never presented as an agent's.
4. **Stewards see only what policy lets them, and the researcher can see who looked.** Visibility is scoped, policy-controlled and audited (C1, C2, C14), never "everything by default".
5. **The shell holds no policy.** What a steward may do is what the harness says is permitted; the shell renders it (App spec).
6. **Nobody has to watch a queue.** Notifications carry a link and a short subject, never research content (#378, #156).
7. **Accessible by keyboard and screen reader.** New states are announced; every hand-over and steward action works without a mouse (#74).

## Vocabulary

| Term | Meaning in this document |
|---|---|
| Escalation | A record attached to a project that hands a matter to a steward (#372). |
| Steward's view | The project as a steward sees it: the researcher's own project view, plainly marked, with the escalation beside it. |
| Pause | A steward's hold on a project so no further consequential step runs until lifted (P4, human-on-the-loop). |

States proposed for an escalation (**[Open]**, #372): `open` → `taken` → `waiting for researcher` → `resolved`, with `handed back` and `withdrawn` as other endings.

## Flow A: the researcher asks for a steward

The researcher can ask at any point in a project, not only after something goes wrong.

1. **Entry point.** A persistent, labelled control in the project, "Ask a data steward", reachable by keyboard from every project page.
2. **Compose.** A short note box (what do you need help with?) and a summary of what will be shared: the project's title, its recent conversation and runs, and the matter in question. The researcher can see the list before sending. **[Open]** the exact default scope (#372, #232).
3. **Confirm.** "Send to a data steward". The researcher is told who will receive it in general terms (the steward team, or the team the profile routes it to) and roughly what happens next.
4. **Waiting.** The project shows an open escalation in a visible but unobtrusive place (the side bar and a marker in the conversation): its state, its age and the note sent. The researcher can carry on working, and can **withdraw** it.
5. **Reply.** The steward's reply appears inside the project's conversation, marked plainly as from a named person ("Steward: Name"), and the researcher is notified (Flow D). The researcher can reply in the same place.
6. **Close.** The steward resolves or hands back with a note. The researcher sees the outcome and can say they disagree or re-open it. **[Open]** whether re-opening is allowed or a new escalation is raised (#372).

Empty and failure states: if the profile names no steward route, the control says so instead of failing silently, and points to the institution's usual contact if the profile supplies one. If a steward does not answer within a time the profile sets, the researcher is told and the matter may be escalated again (#378, **[Open]**).

## Flow B: the agent offers to flag a question

There are three triggers, one pattern: **explain, offer, confirm.**

| Trigger | Example | What the researcher sees |
|---|---|---|
| A `referred` outcome from the policy gate | A run needs approval the profile reserves for a steward | A card in the conversation: why the run stopped, and "Send this to a data steward" |
| An agent abstains or cannot help | No source supports an answer | The abstain card, with the reason, then an offer to ask a steward |
| The orchestrator suggests it | The researcher's questions keep returning to something no agent covers | A message in the orchestrator's voice suggesting a steward, with a button |

The pattern:

1. **Explain.** The agent states, truthfully, what it could not do and why. It never implies it answered when it did not (orchestrator prompt: report abstentions and refusals faithfully).
2. **Offer.** One clear option: "Ask a data steward about this". The offer is a suggestion; the agent does not decide on the researcher's behalf.
3. **Show what will be shared.** The same summary as Flow A, prefilled with the question the agent drafted, which the researcher can edit.
4. **Researcher confirms.** Only then is the escalation created, recorded against the project with its origin (policy gate, agent, orchestrator) so a steward knows why it arrived.
5. **Decline is easy.** "Not now" dismisses the offer. It does not nag; it may be re-offered if the researcher asks again.

Two cases differ slightly:

- **Policy referral.** The run is stopped by the policy and cannot proceed without a steward. The card says so, and the escalation is the next step rather than an optional extra. Whether the steward's approval then resumes the run is open (#16).
- **A discrepancy flagged for human review** (for example R8): the offer names the discrepancy, so the researcher can see what the steward would look at.

## Flow C: the steward's workspace

### C1. The queue

A single place listing escalations routed to the signed-in steward:

- columns: project, researcher, reason (and origin), age, state, who has taken it;
- filters by state; sort by age by default;
- **Take** an escalation, so colleagues see who has it and do not duplicate work;
- keyboard-operable table with clear row focus and announced state changes.

### C2. The project overview (read-only, #232)

Beside the queue, a list of projects the steward may see, with owner, current phase, recent runs and outcomes (including abstentions and referrals), and anything awaiting human review. Which projects appear is decided by the harness from the profile. **[Open]** whether a steward may open any project in scope or only one with an open escalation; the draft proposes escalation-only by default, with the broader overview as a deployment setting, because it discloses a person's work (C2, P4).

### C3. Opening a project as a steward

1. Opening a project shows the **same project view the researcher has**, so the steward sees what the researcher sees.
2. A persistent banner reads "Viewing as a data steward", with the researcher's name and the escalation, and cannot be dismissed.
3. The escalation sits beside the project: the researcher's note, its origin, the history and the steward's own notes.
4. Opening is recorded. The researcher can see "Steward Name viewed this project on date".

### C4. What a steward can do

The closed list proposed in #372. The shell shows only the actions the harness reports as permitted, each with its own explanation. A refused action is explained, not hidden.

| Action | Experience |
|---|---|
| Read the project | Default on opening. |
| Write to the researcher | Reply in the conversation, marked as a person. |
| Approve, edit or reject a proposed change | The existing document-version decision flow ([Projects](../specs/projects.md), #196), with the decider recorded as the steward and a reason required. |
| Run an agent in the project | The same run controls, labelled as run by the steward. **[Open]** whose authority a steward's run acts for (#372). |
| Pause the project | A single labelled control; the researcher sees the project is paused, by whom and why. Lifting it is as prominent as applying it. |
| Resolve or hand back | A note to the researcher is required; the state change is announced. |

Every action is checked by policy and recorded (#374). Where a steward changes a result, the researcher sees what changed and by whom, and can disagree (see Flow A, step 6).

## Flow D: notifications (#378)

- **Steward:** told when an escalation is routed to them. Email first (likely default); a deployment may instead send to its own helpdesk, with the harness record staying authoritative (**[Open]**, #372).
- **Researcher:** told when a steward replies, hands back or resolves.
- **Content:** a link and a short subject only, never research content or personal data beyond what is needed.
- **Choice:** each person chooses what they are told about.

## What the researcher sees, in one place

On a project with an escalation, a single status line answers "what is happening with my request?":

> Sent to the data stewards on 12 November · Taken by Name · Waiting for you to reply

The project also lists who has viewed it as a steward, and any steward actions, in the project's log (the project log already records decisions and membership events, [Projects](../specs/projects.md)).

## Open questions carried from the issues

These are not decided here. Each is owned by the issue shown.

| Question | Owner |
|---|---|
| Roles, and where a role comes from (profile mapping of principals or groups) | #154 |
| May a steward open any project in scope, or only one with an open escalation? Does the researcher consent, or is it a condition of using the deployment? | #232, #372 |
| Which stewards see which escalations: all, or by department, faculty or kind of matter | #372 |
| Whose authority a steward's run acts for; whether the role is recorded on the run | #154, #372 |
| Does an `abstained` outcome raise an escalation, or only offer one? (This draft: offer only.) | #372 |
| Does an escalation lapse or re-escalate after a time? | #16, #378 |
| Can an escalation go to an institution's helpdesk, and is the harness record then authoritative? | #372 |
| Where mail settings and secrets live | #225 |
| Steward visibility by default, to be agreed with the RDA working group (Blueprint §13) | #232, #371 |

## Suggested next steps

1. Use the discovery task (#371) to test these flows with real RDM teams: how do they receive and handle requests today?
2. Fold the settled parts into the spec (#372), and link this document from it.
3. Turn each flow into screens when the spec is Proposed: the researcher's request and agent offer (#375) first, then the steward's workspace (#376).
