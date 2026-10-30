# ADR-0033: The agent roster: one persona per kind of expertise

**Status:** Proposed
**Date:** 2026-10-30

Builds on [ADR-0032](0032-agents-serve-process-steps.md), under which an agent serves steps of the
process flow. Answers the mapping asked for in #311.

## Context

Four advisors existed: standards, policy, repository and quality. Between them they served 10 of
the 30 steps in `dd_sdk.process_flow`. Agents were added as each was needed, so nothing said how
many there should be, where one agent's work ended and the next one's began, or which steps no
agent should take on.

Two designs from the community suggest a roster.

- The Blueprint's AI layer (§9.4, Table 7) names six agents: Planning, Linking, Metadata,
  Repository, Provenance and Validation. Each is broad. The Planning Agent, for example, verifies
  DMP alignment, suggests open formats, and drafts READMEs and data dictionaries.
- Uzwyshyn's persona-based Research Data Director
  ([RDA P27 poster, 2026](https://rayuzwyshyn.net/rda-p27/)) assigns the work to roles a research
  office would recognise: Metadata Librarian, Research Integrity and Ethics Manager, Data Curation
  Librarian, FAIR Expert, Connector, Documentation Editor, and others.

A role that a person would recognise is easier for a researcher to trust, and easier for a data
steward to assess. A narrow role keeps each agent's sources, failure modes and evaluation separate.

## Decision

1. **One agent per persona, named for a kind of expertise.** Each persona is an `advisor.<name>`
   agent that serves the steps listed below and no others. The orchestrators delegate to the
   personas and are not personas themselves.

   | Agent | Title | Serves |
   |---|---|---|
   | `advisor.standards` | Standards Librarian | `setup.vocabularies`, `preparation.formats` |
   | `advisor.documentation` | Documentation Editor | `setup.documentation`, `preparation.documentation` |
   | `advisor.policy` | Policy Adviser | `governance.policies`, `repository.mandated` |
   | `advisor.ethics` | Research Ethics Adviser | `governance.sensitive-data-identify`, `governance.embargo` |
   | `advisor.dmp` | Data Management Plan Checker | `governance.dmp` |
   | `advisor.repository` | Repository Librarian | `repository.recommend`, `repository.pid`, `repository.access-and-costs`, `repository.certification` |
   | `advisor.files` | File Archivist | `preparation.files` |
   | `advisor.metadata` | Metadata Librarian | `preparation.metadata-standard`, `preparation.metadata` |
   | `advisor.quality` | Metadata Reviewer | `deposit.validate` |
   | `advisor.rights` | Rights and Licensing Adviser | `deposit.licence`, `deposit.access` |
   | `advisor.linking` | Linking Adviser | `deposit.links`, `post.links` |
   | `advisor.fairness` | FAIR Assessor | `post.fairness`, `post.retrofit` |

2. **Some steps are left to people and to repositories.** No agent serves
   `governance.sensitive-data-handle`, `deposit.review-link`, `deposit.upload`,
   `deposit.finalise`, `post.institutional-record`, `post.monitor` or `post.embargo-release`.
   Deciding how sensitive data is treated is a person's decision (C2): the ethics adviser flags
   sensitive data and stops there. The other steps act in a repository or an institutional system.
   The orchestrator names them as steps with no agent (ADR-0028 decision 4). Whether a deposit
   persona should take any of them on is TODO(#362).
3. **Provenance is not a persona.** R10 remains the harness's work on every run (ADR-0032
   decision 6). The Blueprint's Provenance Agent and the poster's Provenance Recorder map to the
   run store, not to an agent.
4. **A persona has a title that people see.** `AgentSpec.title` is the persona's name. It is
   carried on the manifest entry as `title` and shown by the app beside the agent id. The
   orchestrator names agents by their titles. A card without a title is still valid, and its agent
   is named by its id. The contract version is unchanged, as it was when ADR-0028 added `serves`.
5. **A persona may start as a mock.** A mock is an ordinary alpha package (`0.1.0a1`). It has its
   own classes, `serves`, title and a card. Its `run` is deterministic (grounding mode `none`) and
   is driven by a small rule table. Its description begins "Mock.", and its payload lists what it
   does not yet do in `limitations`. A mock may not claim any requirement in the requirements
   register. The orchestrator tells the researcher when a result came from a mock.

## Dependencies introduced

None.

## Consequences

- Every step has an agent or an explicit "left to people" decision, so the phase tracker and the
  orchestrators show the whole intended design.
- Each persona's real implementation is its own piece of work and its own issue, and can replace
  the mock's classes when it does. A mock's classes are a sketch, not a published format.
- Two personas may need the same facts about a dataset, for example its fields, which the ethics
  adviser, the documentation editor and the metadata librarian all read. Each declares its own
  input class (ADR-0019). Whether they should share a project record instead is for #194 and #160.
- A persona checking another's draft (the poster's draft-and-critique loop) is not decided here
  (TODO(#309)).
- A new persona is added by amending the table in decision 1.
