# ADR-0036: A person approves or rejects each proposed document version, and the harness records it

**Status:** Proposed
**Date:** 2026-10-30

Answers #196. Builds on [ADR-0017](0017-policy-is-the-deployments.md),
[ADR-0018](0018-acting-for.md), [ADR-0034](0034-project-and-its-files.md) and
[ADR-0035](0035-project-documents.md).

## Context

In the minimum loop of the MVP a researcher checks each draft before it goes into the deposit
package. Blueprint P4 allows agents to "draft and suggest", but no consequential action may
proceed without explicit human approval. C13 asks that agent actions be subject to human
oversight, C14 that designated roles can challenge and override AI outputs, and C15 that human
review be mandatory before submission.

Nothing lets a person approve anything today. Where the profile requires approval for an action
class, the run ends `referred(policy_requires_approval)` and nothing resumes it (ADR-0017).
#71 and #72 planned a full review gate: a general `ProposedAction` for a change to a record in an
external system, risk tiers, rules V0 to V4, batching, and suspending and resuming a run. The MVP
needs only the core of that.

ADR-0035 has settled most of the shape. A project document is a sequence of versions in the
project log (ADR-0034 decision 2). Every version begins `proposed`, a later event can make it
`approved` or `rejected`, and once decided that state does not change. A person's edit is a new
version. The deposit package takes each document's latest approved version (#197). ADR-0035
leaves three questions here: how a decision is made, who makes it, and whether an edit and an
approval may be one step.

Three things constrain the answer:

- **The app holds no policy** (ADR-0024). It renders what the harness decides and records.
- **The caller does not name the human** (ADR-0018). The authentication boundary does. Sign-in
  is deferred for the MVP, so one operator principal is asserted per deployment (#205).
- **A decision must stay tied to what the person saw.** A screen can be out of date, and a
  version approved by mistake from a stale view would go into the package.

#196 and #201 asked for every decision to carry a reason. A reason asked for on every routine
approval tends to become a reflex, which is the approval fatigue that `docs/ui/best-practices.md`
(items 2 and 8) warns about. This record asks for a reason where it explains a departure from the
draft.

## Decision

1. **In the MVP, the only proposed change is a document version.** An agent proposes a document,
   or a change to one, by returning a `Document` payload. The conductor records it as a `proposed`
   version (ADR-0035 decisions 4 and 5). No agent performs a write or holds credentials to write
   anywhere. The general `ProposedAction` of #71 is not adopted. It waits for the first agent
   that would change something outside the project, TODO(#72). The core contract does not
   change.

2. **A decision is `approved` or `rejected`, and a departure from the draft needs a reason.**
   - Rejecting a version requires a reason.
   - Editing a version and approving the edit (decision 3) requires a reason.
   - A plain approval may carry a reason, and need not.

   A reason is free text a person wrote. It is not empty and has a length limit that the
   harness sets. The harness refuses a decision that lacks a reason it requires. Whether some
   approvals must also carry a reason, by risk tier, is TODO(#72). A list of reasons to choose
   from is TODO(#73).

3. **Editing then approving is one request and two events.** The person sends the edited text,
   the version it was edited from, and a reason. The harness appends, in one write, the person's
   version (ADR-0035 decision 4) and then the approval of that new version. Either both events
   are recorded or neither is. The version edited from keeps its own state, which is normally
   still `proposed`. A person may also edit without approving, and the edit then waits as any
   other proposed version does.

4. **A decision names exactly the text the person saw.** A decision request names the version
   as `{document_id, version}` and gives the SHA-256 digest of the text shown. The harness refuses
   the request with a Problem Details response (ADR-0004) in any of these cases:
   - the version is not the document's latest;
   - it has already been decided;
   - the digest is not the version's;
   - the document is not in the request's project.

   Each refusal is recorded in the project log. A person who was looking at an older version
   sees the refusal and the latest version, and decides again.

5. **The decider is the principal the authentication boundary names.** The harness takes it from
   the authenticator (ADR-0018, ADR-0029) as it takes `acting_for` for a run. A decision request
   cannot name a decider. While sign-in is deferred, the decider is the deployment's operator
   principal, recorded with `assurance: asserted`. Within a project, its owners decide
   ([ADR-0037](0037-shared-projects.md) decision 3). Whether a deployment role may also decide is
   TODO(#154). A data steward deciding on a researcher's behalf is TODO(#372).

6. **The harness decides and records, and the app renders.** The harness appends a
   `document_version_decided` event to the project log. The event holds:
   - the version and its digest;
   - the decision;
   - the reason, if there is one;
   - the decider as a `Principal`;
   - the time.

   The app's server passes the person's request to the harness along with the principal from
   its authenticator. It shows the state it reads back from the log, never a state it inferred.
   The project log is the audit trail of decisions, and the deposit package's audit trail
   includes these events (#197). Like the log's other events, the event's exact shape is the
   harness's format and arrives with the project store (#198).

7. **A decision resumes nothing.** A drafting run ends `succeeded` with a proposed version, so no
   run waits for approval. A decision acts on the project, not on a run, and it is not an
   invocation of an agent. Regenerating a rejected document is a new run. The conductor gives the
   agent the version and the decision on it, reason included, in its input (ADR-0034 decision 6),
   and the agent names that version in `revises`. The input's shape arrives with the drafting
   agents (#200).

8. **The policy gate is unchanged.** `referred(policy_requires_approval)` still means that an
   agent did not run because its action class needs approval first. Approving such a run and
   resuming it is TODO(#16, #72).

9. **Deferred, and where each item goes:**
   - risk tiers, rules V0 to V4 and the resolved action of an external write: #72;
   - batching queued items, explaining tiers and capturing reviewer dwell time: #73;
   - suspending and resuming a run, with A2A `input-required` and AG-UI interrupts: #16 and #72;
   - judgements on a run's output that is not a project document: #16 and #25.

Rejected:

- **#71's `ProposedAction` now.** It would add a general class to the core contract with one use
  that `Document` already covers.
- **A drafting run that suspends until a person decides.** Runs would stay open for as long as a
  person takes, which may be days. The run's outcome would also duplicate the version's state.
- **A reason for every decision.** A reason required on every routine approval becomes a reflex.
  Where an approval needs a reason is better decided by risk tier (#72).
- **Deciding any undecided version, not only the latest.** A stale screen could approve text that
  a newer version had already replaced.
- **The app recording the decision.** The app would hold policy, and the record would depend on
  a component that renders.

## Dependencies introduced

None.

## Consequences

- C13 and C15 gain a mechanism for human oversight of what an agent drafts. Nothing is
  substantiated until #201 builds it and tests it, so `docs/requirements.yaml` and
  `CONFORMANCE.md` stay as they are.
- Every document in the deposit package names who approved it and when. Every rejection and edit
  names why.
- A person who approves a document as drafted is not asked for a reason. A reviewer who approves
  everything unread is therefore not visible from reasons alone. Monitoring how often approvals
  come without edits is #73's.
- The one-step edit and approval means two events are written together. The project store must
  make that write atomic (#198).
- A future contributor must not do any of these without revisiting this decision:
  - let the app write a decision;
  - let a request body name its decider;
  - change a decided state;
  - accept a decision that does not name the digest of the text shown;
  - let an agent perform a write.
