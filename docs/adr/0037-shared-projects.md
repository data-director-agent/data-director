# ADR-0037: A project is shared by its members

**Status:** Proposed
**Date:** 2026-10-30

Answers #388. Builds on [ADR-0018](0018-acting-for.md), [ADR-0029](0029-signing-in.md),
[ADR-0034](0034-project-and-its-files.md), [ADR-0035](0035-project-documents.md) and
[ADR-0036](0036-proposed-changes-and-approval.md).

## Context

Research data are rarely managed by one person. A principal investigator, co-investigators, a
research associate and a doctoral researcher may each describe part of a dataset, and one of them
approves what is deposited. For the Data Director to support the workflow end to end, the people
on a research project must be able to work in one project: see the same inventory, documents and
decisions, and continue each other's conversations.

ADR-0034 made the project the unit of work. It is an append-only log kept by the harness, and a
conversation belongs to one project. That ADR left who owns a project, and who else may see it,
to #153. As written, #153 makes conversations and runs belong to the person who started them,
and #154 gives a researcher only their own work. Built that way, one researcher per project would
be fixed in the conversation and run stores before anyone had decided it.

Several decisions already fit a team:

- Every run names the human it acted for, as fixed by the authentication boundary (ADR-0018,
  ADR-0029).
- A person's edit to a document names that person and the version it was edited from
  (ADR-0035 decision 4).
- A decision on a version names its decider and the digest of the text they saw, and is refused
  if the version is no longer the latest (ADR-0036 decisions 4 and 5).

Three things constrain the answer:

- **The app holds no policy** (ADR-0024). Who may see or change a project is decided and recorded
  by the harness.
- **An agent is not told whom it acts for** (ADR-0018), and what goes to a hosted model is limited
  by the profile (ADR-0034 decision 7). A conversation with several people must not change that.
- **Stewards are a separate route.** A data steward reaches a researcher's project through an
  escalation and a deployment role (#370, #372), not by joining it.

## Decision

1. **Access follows the project.** Whatever carries a `project_id` belongs to the project, and is
   visible to the project's members and to no one else except through a deployment role (#154,
   #372). That covers its conversations, its runs, its inventories, its documents and the
   decisions on them. A run outside any project, such as a direct run from an agent's page,
   belongs to the principal it acted for alone (#153).

2. **Membership is recorded in the project log.** The log (ADR-0034 decision 2) gains these
   events:
   - `member_added`;
   - `member_role_changed`;
   - `member_removed`.

   Each event names the member as a `Principal`, the role, the principal who made the change, and
   the time. The `project_created` event makes its creator an owner. Like the log's other events,
   the exact shape is the harness's format and arrives with the project store (#198, #389). The
   core contract does not change.

3. **A project has two roles, `owner` and `member`.**

   | A person may | member | owner |
   |---|---|---|
   | read the project: its conversations, runs, inventories, documents and decisions | yes | yes |
   | start a conversation in the project, or add a turn to any of its conversations | yes | yes |
   | add an inventory or documentation (ADR-0034 decisions 4 and 5) | yes | yes |
   | edit a document, as a new proposed version (ADR-0035 decision 4) | yes | yes |
   | leave the project | yes | yes, unless the last owner |
   | approve or reject a document version (ADR-0036) | no | yes |
   | add or remove a member, or change a member's role | no | yes |

   A project always has at least one owner. The harness refuses to remove or demote the last
   one. Project roles are separate from deployment roles (#154). A deployment role never makes
   anyone a member, and what a steward may do in a project is #372's.

4. **A member is added by their principal identifier.** An owner names the person by the same IRI
   the record uses for them (ADR-0018), an ORCID iD for a researcher who signs in with ORCID. The
   person need not have signed in before. No email address is asked for or held (ADR-0029).
   Because one person who signs in by two routes is two principals (ADR-0029), an owner adds the
   identifier the person signs in with. Whether an added person must accept before becoming a
   member, and how they are told, are TODO(#388, #378).

5. **The harness decides who may do what in a project, and the app renders it.** One check in
   `dd_harness` reads the project log and answers whether a principal may take an action in a
   project (#389).
   - The conductor makes the check before it runs an invocation that belongs to a project, using
     the invocation's `acting_for`.
   - The app's server makes the check for every read.
   - A person who is not a member is refused with a Problem Details response (ADR-0004) of status
     404, so that the refusal does not reveal whether the project exists.
   - A member who attempts an owner's action is refused with status 403.

   A membership change is a request to the harness that carries the principal from the
   authentication boundary. As with a decision (ADR-0036 decision 5), a request cannot name who
   made the change.

6. **Conversations are shared.** Any member may add a turn to any conversation of the project.
   Each turn is its own invocation and acts for the member who sent it (ADR-0018), and a delegated
   child acts for that turn's principal. A conversation therefore records who said each thing,
   turn by turn.

7. **Turns are added in order.** A turn names the turn it follows, by that turn's
   `invocation_id`. The harness refuses with status 409 a turn that does not follow the
   conversation's latest turn, or that arrives while another turn of the conversation is still
   running. Each turn's history (ADR-0024 decision 17) is then exactly the conversation as it
   stood. This also stops one person with two windows open from forking a conversation (#390).

8. **The history says who spoke, without saying who they are.** `ConversationTurn` gains an
   optional slot, `turn_speaker`. The harness fills it with a label that is pseudonymous within
   the project, such as "Member 1", and keeps each member's label the same across the project's
   conversations. It is never a principal's identifier or name. An agent can then tell people
   apart without being told who they are (ADR-0018), and no name reaches a hosted model by this
   route (ADR-0034 decision 7). A turn from a steward can carry a label of its role in the same
   way (#372). The slot is additive and optional, so the contract's version rises by a patch step
   (#390). The app shows members each other's names. It reads them from the run store, not from
   the history.

9. **A stale edit is refused, not merged.** A person's edit names the version it was edited from
   (ADR-0035 decision 4). The harness refuses with status 409 an edit whose parent is not the
   document's latest version, as ADR-0036 decision 4 refuses a stale decision. The person sees
   the latest version and edits again. The harness is the only writer of a project's log, and it
   appends one event at a time.

10. **Leaving and removal take effect from then on.** A member who leaves or is removed loses
    access from that event. Their earlier turns, runs, versions and decisions keep their
    attribution, and a run of theirs that is still going finishes, as a run does when a session
    ends (ADR-0029). What a former member may have erased from a project is TODO(#156, #141).

11. **The membership events are the audit of who could see the project.** Reading by a member is
    not recorded separately. Reading by a steward, who is not a member, is recorded (#372).

Rejected:

- **Conversations that members can read but only their starter can continue.** A team would
  split its work across private threads. #372 would still need a way for a steward to write into
  a researcher's conversation.
- **Private conversations, with only the project record shared.** What was said in a
  conversation would be lost to colleagues, as it is lost between one person's conversations
  without a project (#160).
- **Ownership derived from the runs' `acting_for`.** This was #153's proposal. It cannot name a
  member who has not run anything yet, or remove one.
- **Names or identifiers in the history.** An agent would be told whom it acts for, and names
  would go to hosted models with every turn.
- **Membership set in the deployment's profile.** Who works on a research project is the
  researchers' choice, not deployment policy, and a profile changes by review. Whether a profile
  may limit or forbid sharing is TODO(#388).
- **Merging concurrent edits.** A merged text would be a version that nobody wrote or saw.

## Dependencies introduced

None.

## Consequences

- People can work as a team in one project. #153 narrows to runs outside any project.
- Each run in the deposit crate already names the person it acted for (ADR-0018), so the package
  names every member who contributed to it.
- The project store must check membership on every read and serialise appends to each log (#389).
- `ConversationTurn` gains `turn_speaker`, and the orchestrator's prompt must expect more than one
  speaker (#390).
- The app needs a page for a project's members, and must handle a 409 on a stale turn or edit
  without losing what the person typed (#391).
- Members see each other's words and work. The user guide must say so where a person adds a
  member (#391).
- A future contributor must not do any of these without revisiting this decision:
  - let the app decide or record membership;
  - make anyone a member by a deployment role;
  - put a principal's identifier or name in an agent's input;
  - let a turn or an edit be recorded against a state of the project its sender did not see.
