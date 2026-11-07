# Disclosure of generative AI

## Intent and scope

A dataset's metadata record, README and data dictionary are research outputs, published under
the researcher's name. Institutions and publishers ask that any use of generative AI in producing
them be disclosed. A typical policy, the University of Sheffield's *Principles for Using GenAI in
Research and Innovation*, asks for the name and version of the tool, the date it was used,
whether the output was validated, which sections are reproduced verbatim, and the prompt texts.
The Blueprint asks for the same record: R10 (provenance of AI agent actions, with PROV-O), C13
(actions attributable and under human oversight) and C14 (explanations kept alongside metadata
records).

The Data Director answers from its own record. Each run reports the model calls its agent made.
The run store keeps what each call sent. The project log holds every version of a document, who
or what produced it, and who approved it ([Projects](projects.md)). From these, the harness
states for each approved document how it came about, in two forms: a statement a person reads
and can cite, and a PROV-O graph a machine reads.

The disclosure covers a project's approved documents. A conversational reply is not disclosed
this way: it is not published, and its envelope already carries its model calls. Whether a
document should have been drafted with a model is a matter for policy
([Policy and identity](policy-and-identity.md)), not for the disclosure.

## Invariants

1. **An agent reports each model call it makes.** An agent that calls a language model returns
   one `ModelCall` per call, with the provider, the model the response named, when the call was
   made, the token counts and the `dd-prompt-json-v1` digest of what it sent (`dd_sdk.prompts`).
   The conductor puts the calls in the envelope's `telemetry.model_calls`
   (`test_a_model_call_is_in_the_envelope_and_its_prompt_beside_it_only`,
   `test_each_model_call_is_recorded_with_what_it_was_sent`,
   `test_a_call_is_recorded_with_the_prompt_it_sent`).
2. **A prompt is kept by the harness beside the run, and nowhere else.** An agent returns the
   prompts its calls name. The run store keeps them in the run's `prompts.json`. The envelope,
   the trace and the Process Run Crate name a prompt by its digest only.
3. **A prompt is what its call names.** The conductor keeps a prompt only if it hashes to its
   digest. A prompt that does not hash to its digest, a call whose prompt is missing, or a prompt
   that no call names, fails the run with `agent-error`. The calls are still recorded, because
   they happened (`test_prompts_that_are_not_those_the_calls_name_fail_the_run`).
4. **The disclosure is read from the record and changes nothing.** `dd_harness.disclosure` reads
   the project log and the run store, and writes neither. The app shows what the harness returns
   and holds no wording or rule of its own ([The app](app.md)).
5. **Only an approved version is disclosed, and each says how it came about.** For each document
   with an approved version, the latest approved version is followed back through `revises` to
   the run that drafted it. Its origin is one of five:
   - `model`: drafted with a language model and approved as drafted, so the text is model output
     reproduced verbatim;
   - `model_revised`: drafted with a language model, then edited by a person;
   - `template`: drafted by rule, with no generative model;
   - `template_revised`: drafted by rule, then edited by a person;
   - `person`: written by a person.

   A rejected or undecided version is not disclosed; the statement counts the documents still
   awaiting a decision (`test_the_disclosure_says_how_each_approved_document_came_about`,
   `test_only_approved_versions_are_disclosed`,
   `test_a_template_only_project_says_no_generative_model_was_used`).
6. **The statement names the tool, the date, the validation and every prompt.** For each
   approved document, the statement names:
   - the agent and its version;
   - each model and its provider;
   - the date of the draft;
   - whether the text is reproduced verbatim;
   - who revised it;
   - who approved it, when, and the reason they gave;
   - the SHA-256 of each prompt sent.
7. **The graph is PROV-O.** Each version is a `prov:Entity` that `prov:wasGeneratedBy` its run,
   or a person's edit. A revision `prov:wasRevisionOf` the version before it. A run
   `prov:wasInformedBy` each model call. A model call is a `prov:Activity` associated with the
   model, with the prompt as its `prov:hadPlan`. An approval is a `prov:Activity` that
   `prov:used` the version and is associated with the person who approved it. The approved
   version carries schema.org `digitalSourceType` from the IPTC Digital Source Type vocabulary.
   A prompt is identified by its RFC 6920 `ni:` URI, so the graph names it without carrying it
   (`test_the_disclosure_reads_as_prov_o`).

## Boundaries and contracts

**What is trusted.** The harness checks that the prompts it is given hash to the digests the
calls name. It cannot check that they are what the agent sent to the provider, or that the
agent reported every call: an agent is trusted to report its own model calls, as it is trusted
to emit its own spans ([Evidence and grounding](grounding.md)). A model-backed agent is written to
record each call through `ModelCallLog` in the same place it opens its `chat` span.

**Over the wire.** An agent returns its calls in its result and its prompts beside them, as JSON
strings keyed by digest, as spans are, so that protobuf's `Struct` cannot turn an integer in a
prompt into a floating-point number and change its digest ([Transport and tracing](transport.md)).

**The app.** `GET /api/projects/{id}/disclosure` answers with the statement, each document's
account and the PROV-O graph. The project page shows the statement and offers the statement and
the graph for download.

**The deposit package** carries the statement as `use-of-generative-ai.md` and the graph as
`provenance.jsonld`, written when it is built ([Deposit](deposit.md),
`test_a_valid_project_writes_a_package_with_its_audit_trail`). Like the Process Run Crates in
the package, they name each prompt by its digest only.

## Rationale

The disclosure is read from the record, rather than written by an agent or by the researcher,
so that it says what happened and not what anyone recalls. Each fact it needs is already
recorded for another reason: the project log for review, the envelope for audit. The only new
records are the model calls and their prompts.

A prompt is kept beside the run, rather than in the envelope, because it may hold what a
researcher wrote and, for an orchestrator, the whole conversation. The envelope is read widely,
by the app, the trace viewer and other agents through delegation. The run store is read by those
who may read the run. A digest lets the envelope, the crate and a published statement name the
prompt exactly without carrying it. Anyone who holds the prompt can show that it is the one used.

The model named in a call is the one the provider's response names, because a configured alias
or a server-side fallback may resolve to a different model, and the policy asks for the version
used.

PROV-O is the vocabulary R10 names, and RO-Crate, which the Process Run Crate already uses, draws
on it. No standard term says "generated by AI" in metadata. The IPTC Digital Source Type values,
adopted by schema.org's `digitalSourceType`, are the nearest recognised terms. They were made for
media, so they are carried alongside the PROV account, not instead of it.

## Rejected alternatives

- **Prompts in the envelope or the crate.** They would travel wherever the envelope goes, and
  leave with a published crate.
- **A template id and version in place of the prompt.** It does not say what was sent, which a
  disclosure policy asks for, and an agent's prompt carries the input as well as the template.
- **A statement the researcher writes.** It may omit what happened, and the record already holds
  the facts.
- **An agent that drafts the statement.** It would be AI-generated text about AI use, and might
  differ from the record.
- **DataCite contributor roles or CRediT.** Both name people's roles, and publishing ethics (COPE)
  hold that an AI tool is not an author or contributor.
- **C2PA content credentials.** They are made for signed media assets, not for text records that
  are edited and approved in a log.

## Non-functional requirements

- **Privacy.** A prompt may hold personal data a researcher wrote. It is kept only in the run
  store, read only by whoever may read the run, and named everywhere else by digest. How long
  prompts are kept, and how a person's data in them is erased, are not yet decided: TODO(#156).
- **Auditability.** A disclosure can be made again from the log and the run store at any time,
  and a prompt verified against its digest.
- **Accessibility.** The statement is plain prose with headings, readable without the graph.

## Open questions

- Which policy a deployment cites, and in what words its statement is put, from the institutional
  profile: TODO(#477).
- Whether, and how, the statement is offered for the researcher to add to the README or the
  metadata record's description, which they would then approve: TODO(#478).
- Whether a researcher may choose to include the prompts themselves in the deposit package:
  TODO(#624).
- A run that raises after calling a model reports none of its calls, and the grounding linter
  does not check that each `chat` span has a call. Both bear on audit-trail completeness:
  TODO(#26).
- The w3id namespace under which models are named is not yet registered: TODO(#3).
