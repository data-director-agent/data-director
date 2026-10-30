# ADR-0035: Project documents and their versions

**Status:** Proposed
**Date:** 2026-10-30

Answers #195. Builds on [ADR-0019](0019-core-contract-and-agent-owned-classes.md),
[ADR-0024](0024-app-shell.md) and [ADR-0034](0034-project-and-its-files.md).

## Context

The minimum loop of the MVP drafts three documents for a dataset: a metadata record, a README and
a data dictionary (Blueprint R2, R5). A person checks and approves each one before it goes into
the deposit package (#196, #197). The app's right panel is already headed "Project documents"
(ADR-0024 decision 18), but no class describes a document, and nothing records its versions or
whether a person has approved it.

ADR-0034 settles where documents are kept. A project is an append-only log under
`DD_PROJECTS_DIR`, and uploaded content is stored once by digest beside it. Document versions and
approval decisions are named there as events of that log. What remains is the shape of a document,
how its versions arise and are told apart, which states a version can be in, and which of this
belongs to the core contract.

Four things constrain the answer:

- **Payload classes belong to their agents** (ADR-0019 decision 3). The core holds a payload class
  only where the harness or the app must read it without knowing the agent, as it does for `Reply`.
- **The app holds no policy** (ADR-0024). It renders what the harness records.
- **A document is drafted, edited by a person and regenerated**, and the version a person approved
  must stay identifiable after a newer one appears.
- **The kinds differ in form.** A README is Markdown. A data dictionary may be Markdown or CSV. A
  metadata record is JSON that conforms to a repository's schema, such as ORDA's Figshare fields
  or DataCite.

## Decision

1. **`Document` is a core payload class.** It sits in `data_director.yaml` beside `Reply`, and it
   mixes in `Grounded`. The conductor, the app and the package builder (#197) recognise a document
   from any agent by its class, without knowing the agent. Its slots are:

   | Slot | Required | Meaning |
   |---|---|---|
   | `schema_class` | yes | `Document`. |
   | `document_kind` | yes | `DocumentKind`: `metadata_record`, `readme`, `data_dictionary`, `dmp` or `other`. |
   | `document_title` | no | A short name a person can tell documents apart by, such as "README for `raw/`". |
   | `media_type` | yes | The media type of `document_text`, such as `text/markdown`, `text/csv` or `application/json`. |
   | `conforms_to` | no | The URI of the schema or profile the text follows, such as a repository's metadata schema. |
   | `document_text` | yes | The content of the document, as text. |
   | `document_derivation` | yes | How the text came about (`Derivation`). |
   | `revises` | no | The version this one replaces (decision 3). |
   | `grounded_on` | yes | As for every payload. |

   An agent may return its own payload class, but only a `Document` payload becomes a project
   document. The core contract's version changes for this addition (ADR-0019 decision 1).

2. **Content is text.** Every kind is text with a media type, and a structured record, such as a
   metadata record, is serialised. Validating a metadata record against its `conforms_to` schema
   is the validator's work (R4, #19), not the contract's. The project store keeps the text once
   by its SHA-256 digest under the project's `blobs/` (ADR-0034 decision 2), and each event names
   the digest.

3. **A document has its own identity.** A project may hold several documents of one kind, such as
   a README for each folder. The conductor mints a `document_id` (UUIDv7) when it records a
   `Document` that has no `revises`. A version is identified by its document and a number counted
   from 1 within that document. To regenerate a document, an agent is given the current version
   in its input (ADR-0034 decision 6) and names it in `revises` as `{document_id, version}`. The
   conductor refuses a `revises` that names no version of the run's project, with a Problem
   Details response (ADR-0004), and records the refusal.

4. **Each version is an event of the project log, and none is removed.** A version is added in
   one of three ways:

   - **An agent drafts it**: a run with no `revises`.
   - **An agent regenerates it**: a run whose payload names `revises`.
   - **A person edits it**: the app sends the new text and the version it was edited from, and the
     harness records a version that names the principal and the parent version. It names no run
     and is not grounded, since a person wrote it.

   An agent's version names the run's `invocation_id`, so its grounding, evidence and trace are
   found in the run store. Deleting versions is TODO(#141), with the project itself.

5. **The conductor records an agent's draft.** When a run that belongs to a project succeeds with
   a `Document` payload, the conductor appends a `document_version_added` event to the project
   log. A run that does not succeed adds no version, whatever it returned. The app never writes
   the log. It reads it and draws the right panel from it.

6. **A version's state is its own, and is final once decided.** Every version begins `proposed`.
   A later event may make it `approved` or `rejected`, and after that it does not change. A newer
   version does not alter an earlier version's state, so the version a person approved stays
   identifiable. A document's current version is its latest. The deposit package takes each
   document's latest approved version (#197). A person's edit is a new `proposed` version, and
   approving it is a separate act. How the decision is made and by whom, including whether an
   edit and an approval may be one step, is #196's. Until that decision is in place, the app shows
   every version as "Proposed, not reviewed".

7. **The core holds the class, the harness holds the record.** The contract gains `Document` and
   `DocumentKind`. The events of the project log, `document_version_added` among them, are the
   harness's format and arrive with the project store (#198). What an agent writes in the text,
   and which `conforms_to` it targets, are the agent's.

Rejected:

- **A mixin that each agent's payload class includes.** The harness would have to know every
  agent's class to find the text, and a richer class gains nothing the package can use.
- **One document of each kind per project.** It cannot hold a README for each folder, and the kind
  would have to stand in for an identity.
- **A metadata record as a JSON object in the payload.** One class would then have two shapes of
  content, and the schema it conforms to would still be checked by the validator.
- **A person adding a draft to the project by hand.** The record would miss drafts that a person
  was shown and did not add, and the app would write the log.
- **A state held per document.** A new version would hide which version had been approved.

## Dependencies introduced

None.

## Consequences

- The right panel, the package builder and the orchestrator read one class for every document,
  whichever agent drafted it.
- A person can see every version of a document, who or what produced it, and which one they
  approved.
- The grounding linter checks agent-produced versions only. A person's edit carries no grounding
  by design, and the audit trail names the person instead.
- Text a person uploads or edits may hold personal data. Detecting it is TODO(#39). A document
  given back to an agent counts as `documentation` under the profile's `hosted_models` key
  (ADR-0034 decision 7).
- A future contributor must not let the app write the project log, let a decided state change, or
  make a project document from a payload class other than `Document`, without revisiting this
  decision.
