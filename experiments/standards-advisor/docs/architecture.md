# Data Director R3 Prototype — Architecture

**Derived from:** [`docs/BLUEPRINT.md`](../../../docs/BLUEPRINT.md) — *Data Director Agentic AI
Blueprint*, v1.0 FINAL

**Scope:** Requirement R3 — suggest suitable vocabularies, ontologies and open data formats

## Standards Advisor agent

Functional requirement 3 (R3) from the Data Director Blueprint says the system must look at a
dataset and suggest the standards that would make it easier to share and reuse: controlled
vocabularies for the values in its columns, ontologies for its structure, open file formats, and
standards for how individual values are written, such as dates and units. It is a MUST-have
requirement.

Functional requirement 3 (R3) specifies that the Data Director must "suggest appropriate
vocabularies, ontologies and open data formats."

> Recommend suitable controlled vocabularies, ontologies and file formats, including field-level formats
> such as date/time standards, for a given dataset to improve consistency, interoperability
> and discoverability. Must support emerging standards and new mappings. Must distinguish
> between ontology alignment and controlled vocabulary concept linkage.

This document sets out an over-arching plan for an experimental prototype of an approach to building this functionality.

---

## 1. Scope and purpose

The Blueprint says *what* the Data Director must do, *how well* it must behave, and *what parts* a
full system would need. It does not say what to build first, what goes in and what comes out, or how
you would know whether the thing you built works. This document answers those three questions for
one requirement.

It is **not** a reference implementation of the Data Director, and should not be presented as one.
The Blueprint is explicit that none exists. What it is is a [**slice**](glossary.md#project-and-document-names): a single requirement taken
end to end, thin enough to build quickly and complete enough to test, and built to be replaced if
something better appears.

The Blueprint requires that the results be trustworthy. This means we must implement self-checks and mandatory human review, audit trail, and challengeable explanations.

### 1.2 Stop conditions

Any one of these means stopping and writing up
what we found:

- **The registry does not separate ontologies from controlled vocabularies.** R3 must tell those two
  apart, and §5.2 does it by reading the label FAIRsharing's own curators already put on the record —
  its subtype — rather than by asking the model to judge. That only works if the subtype is actually
  filled in and applied consistently. If it is not, we try exactly one fallback: the record's
  declared serialisation, where OWL points to an ontology and SKOS or OBO to a vocabulary. That is
  still a field in the registry, so the classification still comes from curated data rather than from
  the model. If the serialisation cannot do it either, the one distinction the Blueprint explicitly
  requires has no dependable mechanical basis, and the design needs rethinking rather than patching.
- **The registry's subject and domain lists cannot be fetched by a program.** R3.5 says no built-in
  list of standards. If those lists have to be copied into our code, R3.5 cannot be met as written.
- **Searching by subject finds almost nothing outside the life sciences.** If nearly every run from
  a social science, humanities or engineering dataset comes back empty, the tool is not useful to
  the university it was built for, whatever its accuracy on the runs that do return something.

### 1.3 Limitations

Building one requirement in isolation says nothing about how a full Data Director should arrange its
agents: how they hand work to each other, how they keep track of a conversation, how one persona
decides to call another, or how you keep an agent that *takes actions* safe. §4.2 deliberately
squashes the Blueprint's two agent personas into one plain service. That is the right call for R3,
and it is exactly why this experiment cannot answer those questions — but it says nothing about how
much latitude the model should have *within* that one service, which is a separate question and the
one §5.6 now addresses.

We aim to test whether recommendations can be grounded in a registry.

### 1.4 Assumptions

- **Language and tools:** Python, for the libraries and for the skills a university RSE team already
  has. Nothing in the design depends on it — everything going in and out is plain JSON.
- **Where it runs:** one container, on a local machine. Not a placeholder: it is the Blueprint's
  default position (local first, cloud only where needed) and it keeps the prototype runnable on a
  laptop.
- **Model access:** any chat model with a broadly standard API, reached through one narrow interface.
  Which model was used is recorded with every run, and switching model or provider must not mean
  changing the pipeline. Nothing in the design may depend on a particular vendor's behaviour.
- **Test data:** public deposits from FigShare or Zenodo, available through public APIs. Nothing behind a login, nothing restricted. The profiler reads the *head* of a data file — enough rows to infer column types — not whole files.
- **Data handling.** Sending research data to a hosted model would raise C2 and C4 questions this
  experiment is not set up to answer. So: the parts that read file contents (§5.1 tier 1) run
  locally with no model involved, and only the dataset's own description and derived column
  *metadata* — names, inferred types, counts — are ever sent to a model. Sample values are not. That
  is a constraint on the design, not a note about this prototype's test data.

  The line this draws is **declared schema versus observed data**, and §8 makes that explicit
  rather than changing it. A data dictionary's *declared* permitted values and variable
  definitions may reach a model: a codebook entry is a statement the researcher wrote about what
  may be recorded, not an observation of anything or anyone, and it is precisely what R3.1 needs
  in order to match a vocabulary before any data exists. A value read out of a real file may not,
  whatever its apparent innocuousness. The two live in separate fields of the profile
  (`permitted_values` and `example_values`) so that `nodes/explain.py::_profile_digest` can
  admit one and refuse the other, and so that a test can assert it.

---

## 2. Requirement R3

R3 (priority **MUST**), verbatim from the Blueprint:

> Recommend suitable controlled vocabularies, ontologies and file formats, including field-level
> formats such as date/time standards, for a given dataset to improve consistency, interoperability
> and discoverability. Must support emerging standards and new mappings. Must distinguish between
> ontology alignment and controlled vocabulary concept linkage.

This may be further broken down further into specific requirements as shown in the table below.

| Sub-ID | Obligation | How we know it works |
|---|---|---|
| **R3.1** | Recommend **controlled vocabularies** for pinning the *values* in a column to agreed concept identifiers — e.g. a `language` column to ISO 639 terms, or a `species` column to organism terms | For a dataset with at least one categorical column, returns at least one vocabulary that resolves to a live registry record, naming the column it applies to |
| **R3.2** | Recommend **ontologies** for matching the dataset's *structure* — its variables and how they relate — to classes and properties | Returns ontology recommendations clearly marked as a different kind from R3.1, naming the part of the structure being matched rather than a column's values |
| **R3.3** | Recommend **open formats** for datasets and files — CSV or Parquet instead of XLSX, NetCDF instead of a proprietary binary | For each format found in the input, returns either an open alternative with a registry record, or an explicit "this one is already fine" |
| **R3.4** | Recommend **standards for how values are written** — dates, coordinates, units, country and language codes | For each column that looks like a date, a place, a quantity with units, or a code, names a standard (ISO 8601, ISO 6709, UCUM, ISO 3166, ISO 639) with a registry record where one exists |
| **R3.5** | Support **new and emerging standards** — no fixed built-in list; resources still in development show up, with their status visible | Subject and record-type lists are read from the registry at query time, never written into our code. A resource registered after the prototype was built is findable without a code change |
| **R3.6** | **Say nothing** where there is nothing good to say, rather than producing a vague answer | For a dataset from a field with no registered vocabulary, returns a clear statement that it found nothing, not a weak suggestion |

R3.6 is not in the R3 text. It comes from three other places in the Blueprint that bind R3: R2's
requirement to state plainly where no controlled vocabulary exists for a field of research; C15's
requirement that low-quality or generic outputs be flagged with human review mandatory; and the
Blueprint's own observation that in fields with no history of FAIR practice the tool's output will
be generic, and it should say so rather than dressing it up as domain-appropriate.

Treating "found nothing" as a proper answer rather than an error is the most consequential decision
in this document. See §5.5.

### 2.1 Vocabulary linkage and ontology alignment

The Blueprint requires R3 to tell these apart but does not say where the line falls. We put it
between value and structure: [concept linkage](glossary.md#standards-concepts) pins a column's
*values* to agreed concept identifiers, [ontology alignment](glossary.md#standards-concepts) maps
the dataset's variables and shape onto classes and properties.

They go wrong in different ways and are useful to different people. Running them together — which
most vocabulary recommenders do — is exactly what R3 forbids, so they are separate kinds of output
with different required fields (§6).

---

## 3. Applicable Blueprint controls

As well as its requirements, the Blueprint lists [controls](glossary.md#requirement-and-control-identifiers) —
things every Data Director component has to do, no matter what job it does. A few of them do not
make sense for a small advisory prototype.
The table below picks out the ones that do, says what we build for each, and asks how hard it would
be to add later. That last question sets the order of work. A few can wait. The ones marked **No**
cannot be added later at all: by the time you go looking, the evidence C12 needs is gone, and C15 is
baked into the shape of the system rather than switched on at the end. Both get built from day one.
After the table we list the controls we are skipping, so that they read as decisions we made rather
than things we forgot.

### 3.1 Non-functional requirements

The Blueprint makes every control a *must*. So the MoSCoW column is **ours, not the Blueprint's**:
MUST is what a v0.1 slice has to get right for its results to mean anything, SHOULD is what makes it
usable, COULD is what we would take if it comes cheap. Each control links to its full wording in
[§7.2 of the Blueprint](../../../docs/BLUEPRINT.md#72-non-functional-requirements).

| Control | MoSCoW | What we build | Later? |
|---|---|---|---|
| [**C12**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Data governance — provenance tracking and audit logging | **MUST** | A PROV-O record per run (§6.3) | **No.** Cannot be reconstructed after the fact; the classic thing that never gets added later |
| [**C15**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Quality — self-checks, generic output flagged, human review mandatory | **MUST** | Confidence scoring, the grounding and evidence checks, and saying nothing when there is nothing to say (§5.5). Every output states that a human must review it | **No** — this is the architecture, not a setting |
| [**C14**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Explainability — human-readable explanations, challengeable | **MUST** | A plain-English reason, the registry facts behind it, and a followable link per recommendation. Versioned prompts in the repository | Medium |
| [**C5**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Interoperability — established standards, open APIs | **MUST** | Accepts the metadata a general-purpose repository such as FigShare or Zenodo already provides; produces JSON with a published schema. No formats invented here | Costly — changing the output format breaks anything reading it |
| [**C13**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) AI governance — actions logged, attributable to an agent identity, under human oversight | **SHOULD** | Advisory output only. Agent identity set in configuration and written into every run record. R3 has no irreversible actions to block | Low, given the run record |
| [**C8**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Resiliency — degrade gracefully | **SHOULD** | A local copy of the registry; when the live service fails we answer from it and say so | Medium |
| [**C17**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Affordability — agents must not duplicate work | **COULD** | Profiles and recommendations cached against a fingerprint of their input; the local registry copy shared between runs | Medium |
| [**C10**](../../../docs/BLUEPRINT.md#72-non-functional-requirements) Performance — visible progress, response times suited to the work | **COULD** | A line of progress per stage. One dataset in under a minute | Low |

**Deliberately out of scope**, written down here rather than left unsaid: C1 (infrastructure
encryption — runs locally on public data), C4 (sovereignty, beyond recording which model endpoint is
called), C6 (WCAG 2.1 — see §4.4), C7 and C9 (uptime and availability, meaningless for a local
tool), C11 (scaling across machines) and C16 (usage measurement).

---

## 4. System design

### 4.1 Architectural layers

The Blueprint's reference architecture has five layers and assumes a system built from nothing.
Rather than building one layer properly, this slice builds a rough version of all five at once — a
narrow path from end to end. That tests the connections between the parts early, and the connections
are where the risk is.

```
PRESENTATION   Output viewer — recommendations, the evidence behind them,
               and what the system declined to recommend

APPLICATION    A small API: profile a dataset, ask for recommendations, fetch a past run.
               Something to run the stages in order, saving each result

AI             Profiler (description and files → a description of the dataset)
               Retrieval and ranking, which the model may direct and weigh in on (§5.6)
               Explainer (writes reasons for the recommendations that make it through)
               Model access
               Cleaning of untrusted input, and defence against instructions hidden in it
               An offline test harness — never in the path of a live request
               Nothing the model names can leave the system without passing grounding and
               evidence checks against the registry (§5.5)

DATA           A dated local copy of the registry
               A run log that is only ever added to
               Storage for dataset profiles and runs

INTEGRATION    Registry access (§7)
               Repository access (FigShare, Zenodo) — for building test data only, never a live dependency
               Credential storage — never in prompts, never in logs
```

### 4.2 Single service, two personas

The Blueprint splits R3's work between two agent personas: format advice with a Planning Agent,
vocabulary and ontology advice with a Metadata Agent. But R3 is one requirement, so a test for R3
would have no single component to point at, and the two halves would drift apart.

We build R3 as one service and treat the personas as presentation. A system organised around
personas can call this one service from two conversations without splitting it.

### 4.3 Component responsibilities

| Component | Does | Must not |
|---|---|---|
| **Profiler** | Turns whatever the researcher has — a description, a metadata record, a file listing, column headers, the head of a file — into a structured description of the dataset | Recommend anything |
| **Registry access** | Fetches the registry's own lists of subjects and record types, and retrieves candidate records | Rank, filter for relevance, or interpret |
| **Retriever** | Builds and runs registry queries — the model may propose additional queries or refine filters — returning a candidate set, each candidate remembering which query found it | Return anything as a candidate that did not come back from an actual registry query |
| **Ranker** | Scores candidates against the profile; the default is explicit, versioned rules (§5.3), and the model may propose an adjustment or an additional signal, recorded and attributed like any other score contribution | Produce a score with no recorded, checkable rule or attributed judgement behind it |
| **Explainer** | Writes the plain-English reason for the recommendations, and proposes which column or structure each applies to | State a fact, or name a resource, that the checks stage cannot verify against a registry record |
| **Checks** | Runs the grounding, evidence, confidence and coverage checks, and writes the "we found nothing" statements | Be switched off in configuration |
| **Run record** | Writes down what happened, including which stages the model influenced and how | Be optional |

### 4.4 Output viewer

An instrument for inspecting runs, not a product. It shows recommendations grouped by kind, so the
vocabulary/ontology distinction is visible in the grouping. For each one: the reason, the evidence
with links to sources, how the score was arrived at, any caveats, and the resource's status. It gives
equal prominence to what the system declined to recommend, and it can export a whole run.

It does not meet C6 (WCAG 2.1) at v0.1. That must be stated on the screen itself rather than quietly
left out, and it is why the viewer is for our own inspection and not something to put in front of
participants.

---

## 5. Processing pipeline

Seven stages. Each can be tested on its own, each saves its result, and each adds to the run
record.

```
input → elicit → profile → retrieve → rank → explain → check → recommendations
          ↕                                                   ↳ or a statement that nothing
     (asks the researcher, where                                 qualified
      there is no data to read — §8)
```

`elicit` belongs to §8 and has something to ask on only one of the two entry points. It runs on
every path regardless, returning immediately where there is nothing to ask, so that the stage
list does not depend on the input — see §8.3.

### 5.1 Profile

This stage turns whatever the researcher has into a structured description of the dataset. It is the
only stage that touches file contents, and everything the later stages search on comes from here, so
a profiling mistake shows up as a retrieval mistake unless the profile records how each of its own
statements was arrived at.

Three ways of pulling information out, in order of how much we trust them:

1. **No model needed, runs locally.** File formats from extensions and the first few bytes of each
   file. Column headers. Column types worked out by parsing sample values from the head of the file
   — dates, numbers with units, categories with few distinct values, free text, identifiers,
   coordinates. Distinct-value and blank counts per column. Any metadata that came with the dataset.
2. **Model-assisted, but constrained.** Subject, field of research and entity scope (§5.2),
   expressed only in terms from the registry's own lists, fetched at query time and given to the
   model as a fixed set of choices. The model picks from the list; it does not write labels of its
   own, and picking nothing is a permitted answer.
3. **Model-assisted, and flagged as such.** Measured variables pulled from the free-text
   description, likely instrument, assay or collection method. These widen the search, and each is
   marked *inferred* so its influence can be traced.

Tier 1 is where the file contents stay (§1.4): values are read locally and only derived column
metadata moves on.

There is a **second route into the profile**, for the entry point where none of the above can run
because no data exists (§8.2). It reads a README and a draft data dictionary instead of files, and
it produces the same `DatasetProfile` — so the four searches, the ranking and the checks are
unchanged and unaware of it. What differs is the derivation on every statement: `LOCAL_PARSE`
where tier 1 parsed a value, `DECLARED_IN_DATA_DICTIONARY` where a researcher wrote down what a
column will hold, and `RESEARCHER_ANSWER` where they were asked outright.

Those last two are the *strongest* derivations in the enum, not the weakest, which inverts the
reading order of the tiers above. A declaration is not a guess. What it cannot offer is the
corroboration a sample gives — nothing in a dictionary can reveal that a column called
`collection_date` will in fact be filled in with British-format dates — so a plan is never
recorded as a measurement: the observation counts stay empty, and a declared enumeration is kept
as `permitted_values` rather than as a distinct-value count.

Working out column types does more work than it looks like. R3.4 rests on it entirely, and it is both
cheap and reliable: a column recognised as dates by successfully parsing its sample values against a
list of candidate formats gives an ISO 8601 recommendation with near-total confidence and no model
involved at all. Build this before anything else.

### 5.2 Retrieve

This stage fetches a shortlist of candidate standards from the registry. It chooses nothing and
explains nothing — later stages do that.

Rather than one search, it runs **four**, one per kind of recommendation R3 owes. Each sends
different filters to the registry and draws on different parts of the profile:

| Kind | Registry filter | Parts of the profile used |
|---|---|---|
| Controlled vocabulary (R3.1) | Terminology resources, excluding the ontology subtypes | subject, field of research, entity scope |
| Ontology (R3.2) | Terminology resources, ontology subtypes only | subject, field of research, entity scope, measured variables |
| Dataset and file format (R3.3) | Models and formats | subject, formats found *or* formats planned (§8), kind of data |
| How values are written (R3.4) | Models and formats; reporting guidelines | column types worked out above |

[**Entity scope**](glossary.md#standards-concepts) is what separates a vocabulary
covering the right subject from one covering the right subject *and* the right kind of value: a soil
chemistry dataset and a plant physiology dataset can share a subject term and still need different
vocabularies, and so can two social science datasets, one coding occupations and one coding
administrative geographies.

Three things that are not up for negotiation:

- **The lists of subjects and record types come from the registry, not from our code.** They are
  living vocabularies. Writing them into our code satisfies R3 today and breaks R3.5 by the next
  release. Fetch them, cache them, and fail noisily on something unrecognised rather than quietly
  dropping a filter.
- **Every candidate remembers where it came from** — which query, which filters, which copy of the
  registry. Without that, a ranking bug cannot be diagnosed.
- **Status is kept, never quietly filtered out.** The registry marks records ready, in development,
  uncertain or deprecated. New standards must be visible (R3.5) and quality must be flagged (C15), so
  we retrieve everything, show the status, and let the ranker penalise a record rather than the
  retriever hide it. A deprecated standard a researcher is currently using is extremely useful
  information — as a warning.

### 5.3 Rank

This stage uses an **evaluation framework** to put the standards candidates in order to inform
decisions. The default is explicit scoring with **readable rules** rather than an unexamined
judgement. The model may
contribute a signal too — e.g. flagging a candidate as off-topic despite a subject-term match, or
proposing a weight adjustment for a run — but that contribution is recorded as its own named
component of the score, not folded invisibly into a rule's output. Each rule (or model contribution)
contributes a recorded part of the score:

| Rule | What it measures | Notes |
|---|---|---|
| Subject overlap | The profile's subjects against the record's | The main signal |
| Field-of-research overlap | Finer-grained terms | Separates records within the same broad subject |
| Entity scope overlap | The kinds of thing the profile's values name against the kinds the record covers | Separates records within the same field of research. Skipped, not scored zero, where the profile yields no entity terms |
| Community uptake | Named in data policies; how many adopters; membership of a relevant registry collection | Supports the community-specific vs general distinction |
| Repository fit | Recommended or already in use by the target repository, where the profile names one | |
| Maturity | The record's status and how recently it was updated | Deprecated gets a heavy penalty and a flag saying why |
| Specificity | Prefer domain-specific where the subject match is strong; general where the profile's subjects are broad or thin | Aimed at the "the output will be generic" failure |
| Openness | The licence and access conditions of the resource itself | |
| Type match (R3.4 only) | The column type we worked out against what the standard applies to | Almost entirely mechanical |

The **rule weights** live in a configuration file with a version number, recorded with every run. This makes a change to the ranking a visible, attributed, repeatable
event.

### 5.4 Explain

This stage writes what a reader sees. Its job is to say, in language a researcher can act on, why
each candidate was recommended and what part of the dataset it applies to — whether the ranking that
put it there was purely rule-based or the model weighed in earlier (§5.3).

The model is given the profile, the top few ranked candidates **with their full registry records and
score breakdowns**, and the reasoning behind the ranking. For each candidate it produces:

- a **reason**, written for a researcher rather than a metadata specialist;
- the **target** — which column, variable, file or part of the structure it applies to;
- **caveats** — partial coverage, licence restrictions, deprecation;
- **evidence** — each factual statement paired with the registry record and field it came from;
- a **confidence** score, used as one input to the checks and never as the only one.

The prompt lives in the repository with a version number, recorded with each run. It carries three
prohibitions, enforced by checking the output afterwards rather than by trusting the model: name
nothing outside the candidate set; state no fact about a resource that is not in the record supplied;
say when something is uncertain rather than deciding it.

### 5.5 Check

This stage decides what is fit to leave the system. Four checks run in order, the first two
mechanical and non-negotiable; where a kind of recommendation does not survive them, the stage
writes the statement that says so. This is where C15 is met.

1. **Grounding (must pass).** Every recommendation must carry a registry identifier and DOI that was
   in the candidate set. Anything failing is dropped and logged as a bug, not shown with a warning.
   Target zero. Anything above zero is a defect report.
2. **Evidence (must pass).** Every factual statement in the reason must be backed by an evidence
   entry naming a registry record and field, and those references must resolve. A mechanical check
   on the references, not an attempt to understand the prose. Unbacked statements are removed and
   the removal logged.
3. **Confidence floor (configurable).** Candidates below the threshold are kept out of the main
   list — dropped, or shown in a clearly labelled low-confidence section.
4. **Coverage.** If a kind of recommendation was asked for and nothing survived, say so plainly:
   what we looked for, what we searched (queries, filters, which copy of the registry), why nothing
   qualified, and what the researcher should do instead — usually talk to a specialist in their
   field or the Library RDM team, or consider registering a resource themselves.

These statements sit alongside the recommendations in the output, not in an error field. A run that
finds no suitable ontology but confidently recommends a date format is a *good* run, and the viewer
must present it that way.

It is also a cheap version of something the Blueprint leaves open: what an agent should do when it
declines to answer. R3 declining is a decline with a referral — it says why, and points to a person
who can help. Because R3 does nothing consequential, this can be prototyped without the governance
machinery the same experiment would need anywhere else.

### 5.6 Grounding

This isn't a workflow step, but a rule that shapes the overall workflow — and it is narrower than
earlier drafts of this document made it.

> Nothing leaves the system that cannot be traced to a real registry record retrieved by an actual
> query. Within that limit, the model may direct retrieval, weigh candidates, and contribute to
> ranking — it is not confined to writing explanations for a candidate set and order it had no part
> in producing.

The earlier version of this rule forbade the model from choosing or ranking at all. That went beyond
what the Blueprint asks for: nothing in R3's text or in the applicable controls (§3) prohibits the
model from directing a search or judging relevance. What the Blueprint does require — C15's
mandatory quality self-checks, C12's audit trail, C14's challengeable explanations — is that the
*output* be trustworthy and checkable, not that a particular pipeline stage be excluded from
deciding anything.

So the constraint that survives is the one that is actually testable: the grounding and evidence
checks in §5.5 run over the *output*, regardless of which stage — rule, model, or both — produced it.
A made-up standard still cannot pass the grounding check, because that check only asks "is this
identifier in the candidate set the retriever actually returned from the registry?" — a question
about provenance, not about who ranked it highest. This keeps the useful property from the earlier
design (a failure is a retrieval or ranking mistake you can diagnose, not a fabrication you have to
explain away) without asserting a restriction on model agency that the Blueprint never asked for.

What this changes in practice: the retriever may run model-proposed queries as well as the four fixed
ones in §5.2, and the ranker may take a model-attributed score contribution alongside its rule-based
ones (§5.3). What stays fixed: every candidate a recommendation names must have come back from a real
registry query on a real registry, and every factual claim about it must resolve to a field on that
record. Those two are what §5.5 checks, and they are what make a failure diagnosable rather than
embarrassing — not a general prohibition on the model's role.

---

## 6. Output schemas

Written as JSON Schema before any code is written; those schemas are definitive and the sketch here
is illustrative.

### 6.1 Dataset profile

An identifier and content fingerprint; where it came from and when; the lifecycle phase it was
built for (§8); title, abstract and keywords; subjects, fields of research and entity scope, each
with the term, the list it came from, and whether the model picked it from the registry's list;
files, with the format detected and how; columns, with the inferred type, how it was inferred, any
pattern observed, the proportion of blanks and the number of distinct values; measured variables
taken from the description; the target repository if known; and the profiler version.

For a dataset that does not exist yet (§8.2) the same document carries what was *declared* rather
than observed: per column, the declared type verbatim, the variable definition, the permitted
values and any missing-value code; and per dataset, the formats the researcher intends to write,
kept apart from the formats found. The observation counts are absent rather than zero, because
there is nothing yet to count.

Everything inferred records **how it was arrived at**. That is what lets the test harness tell a
profiling mistake from a ranking mistake. There are exactly two ways to carry it — a `Term`, or a
sibling `*_derivation` field — and no third. Title, abstract and keywords each gained one for §8,
because a title read out of README prose and a title copied from a repository record are not the
same kind of statement, and `retrieve` puts both into registry queries as free text.

### 6.2 Recommendations

```json
{
  "run_id": "...",
  "profile_id": "...",
  "requires_human_review": true,
  "generated_at": "2026-09-03T10:04:12Z",
  "registry_snapshot": { "version": "2026-09-01", "stale": false },
  "agent": { "identity": "urn:dd:agent:sheffield-r3", "version": "0.4.0" },
  "ranking_config": "ranking.v1",

  "recommendations": [
    {
      "kind": "controlled_vocabulary_linkage",
      "resource": {
        "name": "NCBI Taxonomy",
        "registry_id": "FAIRsharing.fj07xj",
        "doi": "10.25504/FAIRsharing.fj07xj",
        "record_type": "terminology_artefact",
        "status": "ready"
      },
      "target": { "kind": "field_values", "field": "species" },
      "score": 0.87,
      "score_features": { "subject_overlap": 0.9, "community_uptake": 0.95, "maturity": 1.0 },
      "confidence": 0.84,
      "reason": "The species column holds 12 distinct organism names ...",
      "evidence": [
        { "statement": "Recommended by 40+ registered data policies",
          "record": "FAIRsharing.fj07xj", "field": "recommended_by" }
      ],
      "caveats": ["Covers organisms only; does not cover soil horizon terms"],
      "queries": ["..."]
    }
  ],

  "nothing_found": [
    {
      "kind": "ontology_alignment",
      "reason": "no_qualifying_resource",
      "searched": {
        "facets": { "subject": ["Environmental Science"], "domain": ["soil"] },
        "candidates_retrieved": 7,
        "candidates_surviving_checks": 0,
        "highest_score": 0.31,
        "confidence_floor": 0.55
      },
      "statement": "No registered ontology covers this dataset's variables well enough. Anything we suggested here would be generic rather than suited to this field.",
      "referral": "Talk to a data specialist in this field, or the Library RDM team, before choosing an ontology to match your dataset's structure to."
    }
  ],

  "provenance": "runs/<run_id>/prov.jsonld"
}
```

Two properties earn their place. `requires_human_review` is always present and cannot be set false,
so C15's mandatory review is met by the output format rather than by whoever builds the interface.
And `nothing_found` sits beside `recommendations` rather than inside it, so anything displaying the
output cannot show the recommendations while ignoring what the system declined to do.

### 6.3 Provenance record

A PROV-O graph per run (C12). It holds: an entry per pipeline stage with start and end times;
entries for the input profile, the copy of the registry used, the ranking settings, each prompt and
the output; an entry for the software with its version and agent identity; the links between all of
these; and the model identity, settings and prompt version attached to the right stage.

An estimated energy cost per stage, from token counts, is recorded as an optional extra. Cheap now,
awkward later.

---

## 7. FAIRsharing integration

Every recommendation in this design has to come from somewhere real.
[FAIRsharing](glossary.md) has been provisionally selected as the registry of vocabularies, ontologies and standards. This section covers how we integrate with that platform.

### 7.1 Available access routes

- A **REST API** at `api.fairsharing.org`. Needs an account; ORCID sign-ins must also set a password.
- A **GraphQL API**, described by FAIRsharing as still in development, with a key on request.
- An **OAI-PMH endpoint** for bulk harvesting, described as work in progress.
- **Asking a record page for its data instead of its web page** — request JSON at a record's URL and
  you get its full metadata. No searching, but no account needed either.
- **Licence:** content is CC-BY-SA 4.0, and the terms come back in API responses.

The Blueprint refers to a model context protocol (MCP) server [OxfordCompetencyCenters/fairsharing-mcp](https://github.com/OxfordCompetencyCenters/fairsharing-mcp)
that is maintained by Oxford Competency Centers, wrapping GraphQL as 97
separate tools, needing a free API key. §5.6 no longer rules this out on principle — the model
directing retrieval is within scope now — but we still don't take it on as a dependency at v0.1: 97
loosely-specified tools is a large, unaudited surface for something that must feed the grounding
check (§5.5), and it duplicates work we need to do anyway (§7.2's single access interface has to
exist regardless, so that a route can be swapped or degrade gracefully under C8). We write our own
queries against GraphQL directly, and treat this server as a reference for how to write them and as
useful evidence that the GraphQL route works. Worth revisiting once the retriever actually needs to
run model-proposed queries rather than a fixed four (§5.2) — the interface in §7.2 is where an
MCP-backed implementation would slot in.

### 7.2 A single access interface

§7.1 lists several ways to reach FAIRsharing, each with different limits — some need an account,
some cannot search, some are unstable. Rather than have the rest of the system talk to any one of
them directly, we define one internal interface — fetch the registry's lists, search, fetch a
record, report which copy is in use — with more than one implementation behind it:

- **Direct record lookup.** Asking a record's URL for JSON. Needs no account, so it can be built
  while the access questions are open. It cannot search, so it is used for looking up identifiers we
  already have and for checking that a recommended record still resolves.
- **A dated local copy.** Used for searching, for working offline, and whenever the live service
  fails.
- **GraphQL**, added once we have an account. The expected route for live searching.

REST is a fallback if GraphQL proves too unstable. Adding or swapping a route is a configuration
change, not a rewrite — that is the point of one interface in front of them.

Because the routes carry different fields, each record says which of its fields are actually
populated, and the ranker skips a rule whose inputs are missing rather than scoring it zero. Treating
"this route does not supply that field" as "the field is empty" produces rankings that vary by route
for no visible reason.

### 7.3 Snapshot currency and staleness

- Harvest into a dated local copy on a schedule; one file per date.
- Prefer the live service; fall back to the copy on failure, timeout or rate limit, mark the result
  as stale, and show that date in the interface, not just in a log.
- Record which copy was used with every run. This is what makes runs repeatable — comparing two
  versions of the ranker against a registry that is changing underneath you measures nothing.

### 7.4 Licensing

FAIRsharing content is CC-BY-SA 4.0. Attribution is already handled: every recommendation carries
the record's DOI and URL. Share-alike only bites on redistribution, so using the API to produce
recommendations is fine, but publishing a harvested collection or a fixture set built from one
carries the obligation onto whatever we publish. The clean answer, and our recommendation: publish
only record identifiers and let others fetch the records themselves.

---

## 8. Lifecycle phases and entry points

Everything above assumes a dataset that exists. This section covers the case where it does not.

### 8.1 Where this comes from

§8.2 of the Blueprint sets out a six-phase process flow with three researcher entry points, and
the first of them is before collection begins. Figure 1, verbatim:

> **Figure 1**. Phase 1: Pre-collection Setup. The workflow entry point for researchers starting a
> new project before data collection begins. Shows the initial drafting of data documentation (R5),
> selection of controlled vocabularies and ontologies (R3), and a decision step to create a new
> Data Management Plan or review an existing one.

So R3 is invoked with no data in existence, on the output of **R5** — a README and a draft data
dictionary. R5 is out of scope for this experiment and assumed done; this section is about what
happens when its output arrives at R3's door.

The advice is worth more here than anywhere later, which is the argument for building it at all.
Adopting ISO 8601 before the first row is written costs nothing. Converting a finished
spreadsheet costs a week and loses information.

Two Blueprint requirements bear on how it is done. **R5** names what cannot be inferred and has
to be asked for:

> Elements that cannot be inferred and require direct researcher input include variable
> definitions, units, missing value codes, study design details, and data collection procedures.

And **R10** (MUST) requires that "all actions taken by AI agents on data and metadata" be
recorded so they can be verified and audited. It is a banner across all six phase figures, not a
phase-specific capability. Putting a set of questions to a researcher and acting on the answers
is such an action, so the questions, the answers, and the fact that the profile depends on them
are all in the run record.

§8.2 of the Blueprint also sets the posture, and it is worth quoting because it is easy to get
wrong when building an intake form: "The workflow belongs to the researcher; the Data Director's
role is to assist, recommend, and flag, not to direct or control." Every question therefore says
why it is being asked, and answering nothing is permitted for all of them.

**Note on requirement numbering.** The Blueprint has no sub-requirements — R3.1 to R3.6 are this
document's decomposition (§2), not the Blueprint's. Only R1 to R12 and C1 to C17 are its own.

### 8.2 A second route into the profile

`DatasetProfile` is the pipeline's only interface to the input: nothing after the profile stage
reads the input or touches the filesystem. A pre-collection mode is therefore a new *producer* of
that document, not a second pipeline and not a branch — `retrieve`, `rank`, `explain`, `check` and
`assemble` are unchanged and unaware of it.

The dictionary is read as **Frictionless Table Schema**. C5 says no formats are invented here, and
Table Schema is an open published specification and itself a registered standard, so the input to
a grounded recommendation is as grounded as the output. It is plain JSON, read directly rather
than through the `frictionless` package: a heavy dependency for a type table is hard to justify in
an experiment whose dependency list is part of what is being judged.

Three things about the mapping are worth recording because they were not obvious:

- **Table Schema's `format` is already strptime syntax** for temporal types, so there is no
  translation layer — only a membership test against the patterns tier 1 knows. A valid pattern
  tier 1 does not recognise is itself the R3.4 finding, and is noted rather than dropped.
- **`missingValues` is declared per schema, not per field.** It lands on the profile rather than
  being copied onto every column, because presenting one global declaration as sixteen per-field
  facts would be a claim the schema never made. The empty string survives the read: "a blank cell
  means missing" and "we have no convention for blank cells" are different statements.
- **Nine of Table Schema's fifteen types have no field-level standard we can search for.** The
  structured ones — `object`, `array`, `any` — become `ColumnType.UNKNOWN`, a failure records why,
  and no field-level search runs for them. Filing them as free text and recommending a text
  standard would be worse than saying nothing: it is the R3.6 failure one level down. The rest are
  mapped, and `boolean`, `time` and `duration` gained column types of their own, because how a
  flag, a clock time or an elapsed quantity is written down is a real interoperability question
  with an ISO 8601 answer.

### 8.3 Asking the researcher

Subject, field of research and entity scope are what §5.2 searches on, and with no data they
cannot be inferred at all. §5.1 tier 2 was meant to obtain them by having a model pick from the
registry's own term lists — but with the default registry route `list_terms()` raises, so there is
no list to pick from. Asking is not a weaker substitute for tier 2 here. It is the only honest
source.

That has a consequence to state plainly: at v0.1 every answer is free text, recorded as a term
with **no list name** and the `RESEARCHER_ANSWER` derivation. It is not a controlled term, and
R3.5 depends on the difference staying visible. When a registry route exists, these questions
should offer the registry's own terms as choices — a change to the question set, not to the code.

The elicitation is a **stage in the graph** that pauses, rather than a step before it. That keeps
one run record, one provenance chain and one `thread_id` covering the whole thing, which is what
R10 wants. Three consequences follow, and all three are load-bearing:

- **The graph keeps its one unconditional line.** A conditional edge past `elicit` would make the
  stage list depend on the input, and both the coverage check and §6.3's one-activity-per-stage
  rely on it not doing that. So the node runs on every path and returns early where there is
  nothing to ask, exactly as `profile` does for its unimplemented tiers.
- **A paused node re-runs from the top on resume.** LangGraph replays it, with the pause returning
  the answers instead of suspending. So everything before the pause must be deterministic, which
  is why the question set is fixed, versioned configuration and not anything a model writes: a
  generated question would be generated twice, and the researcher could be shown one set of
  questions and have their answers matched against another. **TODO:** model-proposed follow-up
  questions would have to be produced in a prior stage and read from state on replay. Not
  attempted.
- **A pause is not a stage outcome.** LangGraph's control-flow signals inherit from `Exception`,
  so the scaffolding that records an unexpected exception would otherwise record a pause as a
  degraded stage, write a stage file for a stage that had not finished, and write a second one on
  resume — a run record showing the elicitation failing and then happening. It is re-raised
  untouched instead, and a test pins that.

A run that pauses reports `awaiting_input`, not `incomplete`. Both lack a document, but one is
waiting for a person and the other has stopped, and the manifest is the field a reader trusts to
tell them which.

### 8.4 What the checkpoint now has to do

This is the real cost of choosing an interruptible stage, and it is worth writing down because
nothing before §8 paid it.

Checkpoints used to be write-only. Every run started and finished in one process, and the
checkpoints existed for the property in §5 — each stage saves its result — and were never read
back. Resume was a capability nothing used. Now the checkpoint is written by one process and read
by another, across a pause of arbitrary length, and the round trip has to actually work.

Two things follow. The serialiser records state models by module path, so **moving or renaming a
model breaks resuming an older checkpoint**; the models are allowlisted explicitly and the round
trip is asserted in a test. And resuming re-reads the versioned configuration from disk, so a run
that paused under one set of ranking weights and resumed under another would produce a single run
record covering two versions. That is refused, on the same grounds `PromptLibrary` refuses a
prompt edited in place.

An in-memory checkpointer cannot outlive its process, so a run that would pause is refused up
front rather than after the questions have been answered into a run that cannot continue.

### 8.5 Which kinds a pre-collection run answers

The Blueprint places R3 twice. Figure 1 puts vocabularies and ontologies in Phase 1; Figure 4
puts open format recommendations in Phase 4, alongside data preparation.

A pre-collection run answers **all four kinds anyway**, and says which ones it has brought
forward. Format advice is at its cheapest before anything has been written, so withholding it
until Phase 4 would be faithful to the figure and useless to the researcher. But this experiment
exists to test the Blueprint's claims, so a deliberate deviation from it belongs in the output
where a reader can see it — as a phase number on the recommendation and a sentence in the
abstention — rather than only in a design document.

**TODO:** the Blueprint places R3's field-level half (our R3.4) in no figure at all. It is treated
here as Phase 1, on the grounds that how dates and units are written is settled in the data
dictionary R5 is drafting in Phase 1. That is our reading and should be put to the maintainers.

The referral text differs by phase, because the action does. After the fact, advice about a
vocabulary means migrating values that already exist and a specialist has to help. Before
collection it means writing a choice into a data dictionary and a data management plan — which is
Figure 1's own next step, and something a researcher can do themselves.

### 8.6 What this does not do

The DMP create-or-review decision in Figure 1 is not implemented. It is the third of Phase 1's
three activities and the one R3 has no part in; the abstentions point at it in prose, and nothing
more. Phases 2 and 3 — governance constraints, and repository selection — are not addressed
either, which matters more than it sounds: the Blueprint puts repository selection before metadata
creation because the repository determines the schema and vocabularies that will apply, and a
pre-collection run usually cannot name one. The §5.3 repository-fit rule is skipped in that case
rather than scored zero.

And with the default registry route, a pre-collection run declines all four kinds, exactly as a
collected one does. The profile underneath it is real; the search is what is missing.
