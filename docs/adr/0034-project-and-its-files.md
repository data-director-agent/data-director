# ADR-0034: A project holds an inventory of its files, not the files

**Status:** Proposed
**Date:** 2026-10-30

Answers #194. Builds on [ADR-0005](0005-dataset-profile-and-validation.md),
[ADR-0012](0012-conversation-and-orchestration.md), [ADR-0017](0017-policy-is-the-deployments.md)
and [ADR-0026](0026-model-credentials.md).

## Context

The minimum loop of the MVP starts with a researcher pointing the tool at their files. It then
drafts a metadata record, a README and a data dictionary, has a person approve them, and ends with
a package that is ready to deposit. Every step after the first works on the same set of files, so
the unit of work and the way files are referred to have to be settled before any step is built.

Nothing in the harness or the app holds files today. Each input is one JSON document sent as a
single A2A data part, and `DatasetProfile` (ADR-0005) is filled in by hand. Conversations are
derived from the run store (ADR-0012 decision 4), so whatever a researcher said in an earlier
conversation is lost to the next one (#160). The app's right panel and status bar are already drawn
for a project that has no record (ADR-0024 §18).

Four things constrain the answer:

- **Sovereignty.** Data, prompts, logs, temporary files and backups must stay where institutional
  and national requirements allow (Blueprint P10, C4). A copy of a dataset on a shared service is
  one more place that has to be governed, retained and deleted.
- **Privacy.** The tool detects and flags personal data but never anonymises it (C2). Data files
  are where personal data is most likely to be.
- **Governance.** What leaves the deployment must be declared and controllable (C12, #40). An agent
  declares the models it calls and whether each is `hosted` or `local` (ADR-0026), but nothing
  enforces that declaration yet.
- **The deployment.** The shared VM accepts request bodies of at most 2 MB, and the app's service
  can read no home directory (`deploy/`). A local install can read the researcher's own folders.

What the loop needs from the data files is facts about them: names, sizes, formats, and the fields
of each table. It does not need the bytes.

## Decision

1. **The project is the unit of work.** A project is a record of its own that outlives any one
   conversation. A conversation belongs to exactly one project, and a project may have many. A
   project is shared by its members ([ADR-0037](0037-shared-projects.md)). The
   app mints a `project_id` (UUIDv7) as it mints conversation identifiers (ADR-0024 §17). The
   request and the envelope gain an optional `project_id`, which the conductor fills from the
   conversation and a caller cannot set. This is a change to the core contract (ADR-0019
   decision 1).

2. **The project record is an append-only log kept by the harness.** Each event says what changed:
   the project was created, an inventory or a document was added, a repository was chosen, a
   member was added. Each event names the run or the request that caused it and whom it acted
   for. Document versions (#195), approval decisions (#196) and changes of membership (ADR-0037)
   are events of the same log. The record lives under
   `DD_PROJECTS_DIR`, which has no default (ADR-0022): `<project_id>/events.jsonl`, with uploaded
   content kept once by digest under `<project_id>/blobs/sha256/<digest>`, as schemas are in the
   run store (ADR-0019 decision 7). The run store is unchanged. Conversations are still derived
   from it (ADR-0012 decision 4), and the project is not.

3. **Research data stay where they are.** The project holds an *inventory* of the data files and
   never their content. Each entry gives a path relative to the dataset's root folder, the size,
   the SHA-256 digest, the media type and the PRONOM identifier, and for a table its fields as a
   Frictionless schema. The inventory names the tool and version that made it and when. It is a
   core contract class, `FileInventory`, and every PRONOM identifier a file matched is kept with
   how it was found, since one file often matches several. Its slots follow ADR-0005: each names
   its external URI, and advisor.files reads them.

4. **The inventory is made where the data live.** A local command, in a workspace member of its own
   that does not need the contract to run (ADR-0031 decision 7), reads a folder and writes the
   inventory as JSON. The researcher adds that file to the project. An app installed on the
   researcher's own machine may run the same code on a folder, read only and only under the
   folders the deployment lists. The shared VM lists none. A scanner that runs in the browser and
   sends only the inventory is TODO(#367).

5. **Documentation may be uploaded; data may not.** A researcher may add documentation they
   already have, such as a README, a codebook or a data management plan, as text within a size
   limit and from a list of media types. The profile can refuse uploads altogether. The app cannot
   tell documentation from data, so the upload form and the user guide state the rule, and
   detecting personal data in what is uploaded is TODO(#39).

6. **Agents are given project facts in their input and never fetch them.** The conductor puts into
   an agent's input the parts of the project the agent's input class asks for: inventory entries,
   and the text of an uploaded document with its digest. The input hash therefore covers what the
   agent was shown (ADR-0012 decision 2). An agent has no file tool and no access to the project
   store, and the A2A message stays a single data part. An agent refers to a data file by its path
   and digest.

7. **The profile decides what goes to a hosted model.** Project content falls into two classes:
   `inventory` (the entries of decision 3) and `documentation` (the text of decision 5). A new
   profile key, `hosted_models`, lists the classes that may be given to an agent whose card
   declares any `hosted` model. The conductor refuses any other input to such an agent before it
   is sent, with a Problem Details response (ADR-0004), and records the refusal like any other.
   Where the profile does not set the key, only `inventory` is allowed. File and field names can
   themselves identify people, so this rule limits what leaves but does not show that nothing
   personal did (TODO(#39, #40)).

8. **The deposit package holds no data files.** It holds the approved documents, the inventory,
   the RO-Crate of the dataset, the validation report and the audit trail (#197). The researcher
   adds the data files when depositing, and the inventory's digests show that they are the files
   that were described.

Rejected:

- **Uploading the data to the app.** It makes the deployment a store of research data that has to
  meet every sovereignty, retention and privacy duty for that data, and the VM is not built to.
- **Reading a folder in place on the shared VM.** The service would need the researcher's
  storage mounted on a machine others use.
- **A project that is a conversation.** Whatever a researcher said would still be lost when they
  started a new conversation (#160).
- **A project derived from the run store.** Every change, including adding an inventory or
  choosing a repository, would have to be an invocation of an agent, for no gain in what is
  recorded.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| [fido](https://github.com/openpreserve/fido) | Runtime path, inventory command only | The inventory gives media types from file extensions and no PRONOM identifier; the command's identification is one module. |
| [Frictionless](https://framework.frictionlessdata.io/) | Runtime path, inventory command only | The researcher gives a table's fields by hand, as `DatasetProfile.fields` is given now (ADR-0005). |

## Consequences

- No copy of the research data has to be governed by the deployment. Its record of a dataset is
  the inventory and the documents.
- An inventory made on a laptop is a claim about files the platform cannot see. The digests let
  the claim be checked at deposit, not before.
- A researcher must run a command before the loop can start, until the browser scanner (#367)
  exists.
- The right panel, the phase tracker and the status bar can draw from the project record, and
  the orchestrator can be given the project instead of re-deriving it from the conversation
  (#160, #341).
- Who may see and change a project is settled by ADR-0037: its members. How long a project is
  kept, and what deleting one removes, are TODO(#141), together with the conversations that
  belong to it.
- A future contributor must not accept data files into the project, give an agent access to the
  project store, or send `documentation` to a hosted model by default, without revisiting this
  decision.
