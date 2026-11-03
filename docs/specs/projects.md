# Projects

## Intent and scope

A project is the unit of work of the minimum loop: a researcher describes a dataset, agents draft
a metadata record, a README and a data dictionary (R2, R5), a person approves each one, and a
deposit package is built from what was approved ([Deposit](deposit.md)). Every step after the
first works on the same dataset, so the project is a record of its own that outlives any one
conversation. A conversation belongs to exactly one project, and a project may have many.

A project holds four things:

- an **inventory** of the dataset's files: facts about them, never their content;
- **documentation** a researcher already has, such as a README, a codebook or a data management
  plan, as text;
- **documents** and their **versions**, each version drafted by an agent or edited by a person,
  and the **decision** a person made on it;
- its **members**, who share all of the above.

The harness keeps the project as an append-only log of events, each saying what changed, whom
it acted for and what caused it. The run store is separate and unchanged: conversations are still
derived from it ([Orchestration](orchestration.md)), and the project is not. The log's events and
how they are stored are the harness's format, described in
[`harness/docs/projects.md`](../../harness/docs/projects.md). The inventory command is described
in [`inventory/README.md`](../../inventory/README.md).

Out of scope: research data files, which are never uploaded or read by the platform; actions on
anything outside the project, which no agent performs; a steward's route into a project, which is
an escalation and a deployment role, not membership, TODO(#372).

What is built: the project log with its creation, inventory and repository choice events, reached
through the `dd-harness project` command; document versions and a person's decision on each,
which the app shows and takes at `/projects/{project_id}`; the inventory command; and the core
classes `FileInventory` and `Document`. All of the log is kept by `dd_harness.projects`. The rest of this spec is the
intended design, and each part says where it is not built yet.

## Invariants

1. **The project never holds a data file's content.** An inventory entry gives a path relative to
   the dataset's root folder, the size, the SHA-256 digest, the media type and every PRONOM
   identifier matched with how it was found, and for a table its fields. An absolute path is
   refused, since it would say where the data live. Enforced by the `FileInventory` schema and
   `inventory/tests/test_inventory.py` (no content, no absolute path).
2. **The log is append-only, and the harness is its only writer.** No event is changed or
   removed, including versions and decisions. The app reads the log and never writes it.
   Appends to one project's log are serialised and each event goes in whole and is flushed before
   the call returns. Enforced in part by `harness/tests/test_projects.py`; the serialisation
   holds within one harness process only (`ProjectStore._lock`).
3. **What the store refuses leaves no trace.** An inventory that fails the `FileInventory` class
   schema, or a call on an unknown project, records nothing and keeps no blob
   (`harness/tests/test_projects.py`).
4. **Every event names the principal it acted for and what caused it.** An event caused by a run
   names the run's `invocation_id`; today every event is caused by the command a person ran, and
   naming the run is not built yet, TODO(#394).
5. **The latest counts.** The project's inventory is the one added last; its repository is the one
   chosen last. Earlier ones stay in the log (`harness/tests/test_projects.py`).
6. **An agent is given project facts and never fetches them.** The conductor puts into an agent's
   input the parts of the project the agent's input class asks for: inventory entries, the text of
   documentation or of a document version with its digest, and the merged requirements. The input
   hash therefore covers what the agent was shown. An agent has no file tool, no access to the
   project store, and refers to a data file by path and digest. An inventory's stored digest is
   already its `dd-input-json-v1` input hash. Giving agents project facts is not built yet,
   TODO(#394).
7. **The conductor fills `project_id`.** The request and the envelope carry an optional
   `project_id`, which the conductor takes from the conversation and a caller cannot set. Not
   built yet, TODO(#394).
8. **Only `inventory` goes to a hosted model by default.** Project content is of two classes,
   `inventory` and `documentation` (uploaded text, and any document version given back to an
   agent). The profile lists the classes that may be given to an agent whose card declares a
   `hosted` model; where it does not say, only `inventory` may. The conductor refuses anything
   else before it is sent, with a Problem Details response, and records the refusal. Not built
   yet, TODO(#394, #40).
9. **Only a `Document` payload of a succeeded run becomes a project document.** When a run that
   belongs to a project succeeds with a `Document` payload, the conductor records it as a new
   version. A run that does not succeed adds no version, whatever it returned. Another payload
   class never becomes a document. The store refuses anything else
   (`ProjectStore.record_draft`, `harness/tests/test_project_documents.py`); the conductor
   calling it for each run in a project is not built yet, TODO(#394).
10. **A document has its own identity; a version is `{document_id, version}`.** The conductor
    mints a `document_id` (UUIDv7) for a `Document` with no `revises`; versions are numbered from
    1 within the document. A `revises` that names no version of the run's project is refused with
    a Problem Details response and recorded. The store mints the identity, numbers the versions
    and refuses such a `revises`; the conductor's Problem Details response and record of it are
    not built yet, TODO(#394).
11. **A version's state is its own and final once decided.** Every version begins `proposed`; one
    later event may make it `approved` or `rejected`, and then it never changes. A newer version
    leaves an earlier one's state as it was, so the version a person approved stays identifiable.
    A document's current version is its latest; the deposit package takes its latest approved
    version. Enforced by `ProjectStore.decide` (`harness/tests/test_project_documents.py`).
12. **A decision or an edit names exactly what its sender saw.** A decision names the version and
    the SHA-256 of the text shown, and is refused if the version is not the document's latest,
    is already decided, has another digest, or is not in the request's project (409, or 404 for
    a document not in it). An edit names the version it was edited from and the digest of its
    text, and is refused (409) if that is not the latest. A turn names the turn it follows and is
    refused (409) if that is not the conversation's latest turn, or while another turn of it is
    running. Nothing is merged. Each refusal of a decision or an edit is a
    `document_change_refused` event; a request malformed in itself, such as a rejection without
    a reason, records nothing. Recording a refused turn is not built yet, TODO(#390).
13. **A departure from the draft carries a reason.** Rejecting needs a reason; editing and
    approving in one step needs a reason; a plain approval may carry one. A reason is non-empty
    free text of at most 2,000 characters. The harness refuses a decision without a reason it
    requires, and publishes the rule (`review_rules`) so that the app states it rather than
    holding its own.
14. **Edit-then-approve is one request and two events, written together or not at all**: the
    person's version, then the approval of it, appended in one write. The version edited from
    keeps its own state.
15. **No request names who made it.** The decider, the editor, the person who changes membership
    and the principal of each turn are the principal the authentication boundary names
    ([Policy and identity](policy-and-identity.md)), never a field of the request body.
16. **A project always has at least one owner, and only owners decide or manage members.** The
    `project_created` event makes its creator an owner. The harness refuses to remove or demote the
    last owner. A deployment role never makes anyone a member. Not built yet, TODO(#389).
17. **Access follows the project.** Whatever carries a `project_id` (conversations, runs,
    inventories, documents, decisions) is visible to the project's members and to no one else
    except through a deployment role, TODO(#154, #372). A non-member is refused with status 404,
    so that a refusal does not reveal whether the project exists; a member attempting an owner's
    action with 403. Not built yet, TODO(#389).
18. **No principal's identifier or name enters an agent's input.** A conversation's history marks
    each turn's speaker with a label pseudonymous within the project, such as "Member 1", stable
    across its conversations. Not built yet, TODO(#390).
19. **Leaving or removal takes effect from that event.** Earlier turns, runs, versions and
    decisions keep their attribution, and a run already going finishes. Not built yet,
    TODO(#389).

## Boundaries and contracts

**The core contract** ([Contract](contract.md)) holds `FileInventory`, `Document`, `DocumentKind`
and the version reference, because the conductor, the app and the package builder must read them
from any agent without knowing the agent. A document's content is always text with a media type;
a metadata record is serialised, and `conforms_to` names the schema it follows. Checking a record
against that schema is validation's work ([Deposit](deposit.md)), not the contract's. What an agent
writes in a document, and which schema it targets, are the agent's. The `project_id` on request and
envelope, and the speaker label on a conversation turn, are additive contract changes still to be
made (TODO(#394, #390)). The events of the project log are the harness's format, not the
contract's.

**The harness** decides and records: it keeps the log, applies the access check, records
versions, decisions, refusals and membership. One check in `dd_harness` answers whether a principal
may take an action in a project; the conductor makes it before an invocation that belongs to a
project, using the invocation's `acting_for`, and the app's server makes it for every read.

**The app** ([The app](app.md)) renders the project and passes a person's request to the harness
with the principal from its authenticator. It shows the state it reads back from the log, never a
state it inferred, and holds no policy. The right panel, phase tracker and status bar are drawn
for a project but have no record behind them yet, TODO(#160). Adding an inventory from the app is
TODO(#395); a page for a project's members, and keeping what a person typed when a turn or edit is
refused as stale, are TODO(#391).

**The inventory command** `dd-inventory` is a workspace member of its own that depends on no other
member, not even the contract ([System and boundaries](system.md)); its tests check its output
against the `FileInventory` schema. It runs where the data live. An app installed on the
researcher's own machine may run the same code on a folder, read only and only under folders the
deployment lists; the shared deployment lists none. A scanner in the browser that sends only the
inventory is TODO(#367).

**Documentation** may be added as text, within a size limit and from a list of media types, and
the profile can refuse it altogether. The app cannot tell documentation from data, so the upload
form and the user guide state the rule. Adding documentation is not built yet, TODO(#395).

**Agents** propose; they do not write. The only proposed change is a document version, returned as
a `Document` payload. No agent writes anywhere or holds credentials to. A general proposed action
for a change outside the project waits for the first agent that needs one, TODO(#72).

**Runs and decisions are separate.** A drafting run ends `succeeded` with a proposed version, so no
run waits for a person. A decision acts on the project, is not an invocation of an agent and
resumes nothing. Regenerating a rejected document is a new run, given the version and the
decision on it, reason included, and naming that version in `revises`. The policy gate's
`referred(policy_requires_approval)` is unchanged: approving such a run and resuming it is
TODO(#16, #72).

**Roles.** A project has two roles, separate from deployment roles (TODO(#154)):

| A person may | member | owner |
|---|---|---|
| read the project, start a conversation in it, add a turn to any of its conversations | yes | yes |
| add an inventory or documentation; edit a document as a new proposed version | yes | yes |
| leave the project | yes | unless the last owner |
| approve or reject a document version | no | yes |
| add or remove a member, or change a role | no | yes |

A member is added by the principal identifier they sign in with (an ORCID iD for ORCID sign-in);
they need not have signed in before. Whether an added person must accept first, and how they are
told, are TODO(#388, #378). Each turn of a shared conversation acts for the member who sent it,
and a delegated child for that turn's principal. A run outside any project belongs to the
principal it acted for alone, TODO(#153).

**Audit.** The project log is the audit trail of the project: versions name the run that drafted
them (whose grounding, evidence and trace are in the run store) or the person who edited them;
decisions name the decider, the digest and the reason; membership events are the record of who
could see the project. Reading by a member is not recorded separately; reading by a steward is,
TODO(#372). The grounding linter checks agent-drafted versions only; a person's edit carries no
grounding, and the record names the person instead ([Evidence and grounding](grounding.md)).

## Rationale

- **Data stay where they are.** The loop needs facts about the files (names, sizes, formats,
  fields), not their bytes. A copy on a shared service would be one more place to govern, retain
  and delete under sovereignty and privacy duties (C4, P10, C2). The inventory's digests let the
  files deposited later be shown to be the files described.
- **Facts go into the input**, so the input hash covers what the agent saw, the A2A message stays a
  single data part, and the profile can decide what leaves the deployment (C12).
- **State per version, not per document**, so a newer draft never hides which text a person
  approved.
- **Only the latest version can be decided or edited**, so a stale screen cannot approve or
  overwrite text a newer version has replaced.
- **A reason only where the person departs from the draft.** A reason demanded on every routine
  approval becomes a reflex, the approval fatigue `docs/ui/best-practices.md` warns about. Whether
  some approvals need one by risk is TODO(#72); a list of reasons to choose from is TODO(#73).
- **Human oversight of drafts** (P4, C13, C15): agents draft and suggest; a person decides what
  goes into the package, and every document in it names who approved it and when.
- **Shared projects**, because research data are rarely managed by one person, and colleagues must
  see the same inventory, documents, decisions and conversations.

## Rejected alternatives

- **Uploading the research data**, or reading a folder in place on the shared deployment. Either
  makes the deployment a store of research data, bound by every duty for that data, or mounts
  researchers' storage on a machine others use.
- **A project that is a conversation, or derived from the run store.** What a researcher said would
  be lost when they started a new conversation (TODO(#160)), and every change, such as adding an
  inventory, would have to be an agent invocation for nothing gained.
- **A mixin that each agent's payload class includes.** The harness would have to know every
  agent's class to find the text.
- **One document of each kind per project.** It cannot hold a README for each folder, and the kind
  would stand in for an identity.
- **A metadata record as a JSON object in the payload.** One class would have two shapes of
  content, and the schema would still be checked by validation.
- **A person adding a draft to the project by hand**, or the app recording decisions or
  membership. The record would miss drafts a person was shown and did not add, and the app would
  hold policy.
- **Editing a document in place, or deciding without naming the text.** A decision must stay tied
  to the text the person saw.
- **A drafting run that suspends until a person decides.** Runs would stay open for days, and the
  run's outcome would duplicate the version's state.
- **A general proposed-action class now.** It adds a core class with one use that `Document`
  already covers.
- **Merging concurrent edits.** A merged text is a version nobody wrote or saw.
- **Conversations only their starter may continue, or private conversations with a shared record.**
  A team's work would split into private threads, and what was said would be lost to colleagues.
- **Ownership derived from the runs' `acting_for`.** It cannot name a member who has not run
  anything yet, or remove one.
- **Names or identifiers in the conversation history.** An agent would be told whom it acts for,
  and names would go to hosted models with every turn.
- **Membership set in the deployment's profile.** Who works on a research project is the
  researchers' choice, and a profile changes by review. Whether a profile may limit sharing is
  TODO(#388).

## Non-functional requirements

- **Privacy.** File and field names, uploaded documentation and a person's edits may identify
  people. Limiting what goes to a hosted model limits what leaves; it does not show that nothing
  personal did. Detecting personal data is TODO(#39, #40), and the tool never anonymises (C2).
  No email address is asked for or held for a member. Members see each other's words and work,
  and the user guide must say so where a member is added, TODO(#391).
- **Disclosure.** A refusal to a non-member does not reveal whether a project exists.
- **Durability.** An event is flushed to disk before the call returns, and a blob is written aside
  and moved into place, so a reader never sees half of one.
- **Sovereignty.** The project store lives under a directory the operator names and has no default
  ([System and boundaries](system.md)).

## Open questions

- How long a project and its conversations are kept, and what deleting a project or a version
  removes, TODO(#141).
- What a former member may have erased from a project, TODO(#156, #141).
- What a data steward may do in a researcher's project, and whether a deployment role may decide
  on a version, TODO(#372, #154).
