# Data Director R3 Prototype — Glossary

Acronyms and terms as they are used in this experiment. Where a term has a broader meaning
elsewhere, the definition below is the narrower one that applies here.

Related: [`README.md`](../README.md), [`architecture.md`](architecture.md), and the
[Blueprint](../../../docs/BLUEPRINT.md) itself.

---

## Project and document names

| Term | Meaning |
|---|---|
| **Blueprint** | The *Data Director Agentic AI Blueprint*, v1.0 FINAL — the specification this experiment implements one slice of. Held at [`docs/BLUEPRINT.md`](../../../docs/BLUEPRINT.md) |
| **Data Director** | The full system the Blueprint describes: an agentic AI assistant supporting research data management across the data lifecycle. Not what this experiment builds |
| **R3 prototype / standards advisor** | This experiment. A single requirement (R3) of the Blueprint taken end to end |
| **RDA** | Research Data Alliance — the body under which the Blueprint was produced |
| **Slice** | One Blueprint requirement built end to end through all five architectural layers, rather than one layer built completely. Deliberately thin, deliberately replaceable |
| **Reference implementation** | A canonical, authoritative implementation of the Blueprint. None exists, and this experiment is **not** one |

## Requirement and control identifiers

| Term | Meaning |
|---|---|
| **R*n*** | A *functional* requirement in the Blueprint — something the system must do. This experiment implements **R3** |
| **R3** | "Recommend suitable controlled vocabularies, ontologies and file formats, including field-level formats … Must distinguish between ontology alignment and controlled vocabulary concept linkage." Priority MUST. Verbatim in §2 of the architecture |
| **R3.1 – R3.6** | Our decomposition of R3 into six sub-obligations (§2). R3.1 vocabularies, R3.2 ontologies, R3.3 open formats, R3.4 field-level formats, R3.5 emerging standards, R3.6 abstention. **R3.6 is ours**, derived from R2, C15 and the Blueprint's own commentary — it is not in the R3 text |
| **C*n*** | A *non-functional* requirement in the Blueprint — a control every component must satisfy, listed in [§7.2 of the Blueprint](../../../docs/BLUEPRINT.md#72-non-functional-requirements). The ones in scope here are C5, C8, C10, C12, C13, C14, C15 and C17 (§3) |
| **M0 – M3** | Delivery milestones. M0 is the feasibility check; M1 end-to-end skeleton plus registry access; M2 profiler; M3 rank, explain, check and measure. **TODO:** the delivery plan itself is not written — these names are used in conversation and in `README.md` but no section defines them |
| **MoSCoW** | Must / Should / Could / Won't prioritisation. In §3 the MoSCoW column is **ours, not the Blueprint's** — the Blueprint makes every control a must |
| **Stop condition** | A finding that would mean ending the experiment and writing up, rather than patching the design (§1.2). All three are checked in the first two days |
| **Feasibility gate** | One of the three M0 questions, each mapping onto a stop condition (§1.2) |
| **Obligation test** | An automated test asserting that a Blueprint control still holds — e.g. that mandatory human review cannot be switched off |

## Pipeline stages and components

| Term | Meaning |
|---|---|
| **Elicit** / **elicitation** | Putting a fixed, versioned set of questions to the researcher, where no data exists to infer the answers from, and recording what they said (§8.3). The stage pauses the graph and resumes when answered |
| **Profile** (verb) / **profiler** | Turning a dataset's description, metadata, file listing and file heads into a structured description of it. Recommends nothing |
| **Profile** (noun) | The structured output of profiling — subjects, files, columns with inferred types, measured variables (§6.1) |
| **Retrieve** / **retriever** | Building and running registry queries from a profile to produce an *unranked* candidate set. Four separate searches, one per kind of recommendation (§5.2) |
| **Rank** / **ranker** | Scoring candidates against the profile. Explicit, readable, versioned rules by default; the model may contribute an attributed score component too, recorded like any other (§5.3) |
| **Explain** / **explainer** | Writes the plain-English reason, target and caveats for the recommendations that survive ranking and checks (§5.4). Not the model's only role — see §5.6 |
| **Check** / **checks** | The four post-hoc checks — grounding, evidence, confidence floor, coverage (§5.5). Cannot be disabled in configuration |
| **Candidate** | A registry record returned by retrieval, before ranking. Each remembers which query and which registry snapshot produced it |
| **Candidate set** | The full set of candidates for a run. The model may not name anything outside it |
| **Target** | What a recommendation applies to — a column's values, a variable, a file, or a part of the dataset's structure |
| **Evidence** | A factual statement in an explanation paired with the registry record and field it came from. Checked mechanically for resolvability, not for meaning |
| **Grounding** | The requirement that every recommendation carries a registry identifier and DOI that was in the candidate set. Must-pass; any failure is a defect report |
| **Abstention** / **nothing found** | An explicit statement that no suitable resource was found, with what was searched and a referral. A first-class output sitting beside `recommendations`, not an error (R3.6, §5.5) |
| **Referral** | The person or team an abstention points the researcher to — typically a domain data specialist or the Library RDM team |
| **Confidence floor** | The configurable score threshold below which a candidate is kept out of the main recommendation list |
| **Coverage** | Two distinct uses: the coverage *check* (a requested kind of recommendation produced nothing, so say so), and coverage *by subject* (the share of sample deposits returning any recommendation, broken down by discipline) |
| **Run record** | The per-run audit trail: stages, timings, inputs, prompt and ranking versions, model identity. Append-only. Written as PROV-O (§6.3) |
| **Registry snapshot** | A dated local copy of the registry, used for searching, offline work and fallback. Recorded with every run so that runs are repeatable |
| **Stale** | A result answered from a snapshot because the live registry was unavailable. Must be visible in the interface, not only in a log |
| **Output viewer** | An instrument for inspecting runs (§4.4). Not a product, and explicitly not WCAG 2.1 compliant at v0.1 |
| **Fixture** | A hand-made dataset with a deliberate fault and a known right answer, used as the regression suite and weight-sweep target. "Should find nothing" is a valid right answer. `samples/` holds the two that exist: a collected dataset and a planned one (§8) |
| **Weight sweep** | Searching ranking-weight combinations against the fixtures, instead of tuning weights by instinct |
| **Repeatability** | Same input, settings and registry snapshot → same recommendations, order, scores and check results. Explanation *wording* is exempt |

## Standards concepts

| Term | Meaning |
|---|---|
| **Controlled vocabulary** | An agreed list of terms with identifiers. Used here for **concept linkage**: pinning the *values* in a column to concept identifiers (R3.1) |
| **Ontology** | A formal model of classes, properties and relations. Used here for **alignment**: matching the dataset's *structure* to those classes and properties (R3.2) |
| **Concept linkage** | Value-level mapping — `treatment = "dexamethasone"` → a concept identifier. Produces a value-to-identifier mapping (§2.1) |
| **(Ontology) alignment** | Structure-level mapping — the variable `treatment` → a class or property. Produces a crosswalk between two schemas (§2.1) |
| **Crosswalk** | A mapping between two schemas or vocabularies |
| **Terminology artefact** | FAIRsharing's record type covering vocabularies and ontologies together. Both R3.1 and R3.2 search it; they differ only in the subtype filter |
| **Lifecycle phase** | Which of the Blueprint's six process-flow phases a run serves (§8.1). Only two entry points concern R3, and they differ in whether the data exists yet |
| **Pre-collection** | Blueprint Phase 1 — a project starting, with a README and a draft data dictionary from R5 and no data at all (§8) |
| **Collected** | The entry point where data files exist and can be profiled directly (§5.1). Everything before §8 assumed this |
| **Declared** vs **observed** | Where a statement about a column came from: a researcher wrote it in a data dictionary, or it was parsed out of a real value. The distinction is what §1.4 now turns on — declared schema may reach a model, observed values may not |
| **Data dictionary** | The variable definitions R5 drafts: name, description, type, units, permitted values, missing-value codes. Read as Frictionless Table Schema (§8.2) |
| **Table Schema** | The Frictionless specification for describing tabular fields. Chosen because C5 forbids inventing formats and it is itself a registered standard |
| **Brought forward** | Advice the Blueprint places in a later phase, given anyway because it is cheaper to act on now, and labelled as such in the output (§8.5) |
| **Intake question set** | The questions `elicit` asks, in `config/intake.v*.toml`. Versioned by filename and hashed, like the ranking weights — a run record must resolve to the questions actually put (R10) |
| **Subtype** | The finer classification on a FAIRsharing record. §5.2 reads it to separate ontologies from vocabularies — a label FAIRsharing's curators applied, not a judgement by the model |
| **Serialisation** | The format a terminology resource is published in. The single permitted fallback if subtypes fail: OWL → ontology, SKOS or OBO → vocabulary |
| **Field-level format** | A standard for how an individual *value* is written — a date, a coordinate, a unit, a country or language code (R3.4) |
| **Open format** | A format with a public specification and no proprietary dependency — e.g. CSV or Parquet over XLSX, NetCDF over a proprietary binary (R3.3) |
| **Status / maturity** | A registry record's lifecycle state: ready, in development, uncertain, deprecated. Never filtered out at retrieval — retrieved, shown, and penalised by the ranker |
| **Specificity** | The ranking rule preferring domain-specific resources on a strong subject match and general ones where the profile's subjects are broad or thin. Aimed at the "the output will be generic" failure |
| **Field of research** | A finer-grained subject term from the registry's own list, used to separate records within one broad subject |
| **Entity scope** | What kinds of thing a dataset's *values* name — organisms, chemical substances, places, languages, occupations, materials, instruments, institutions. Distinct from subject: two datasets can share a subject and still need different vocabularies because they name different kinds of thing. Expressed only in the registry's own facet terms, and dropped rather than guessed where a profile yields none (§5.2). Organisms are one case of it, not the general one |

## Registries, services and protocols

| Term | Meaning |
|---|---|
| **FAIRsharing** | The curated registry of standards, databases and data policies that every recommendation must resolve to. The riskiest connection in the design (§7) |
| **FAIR** | Findable, Accessible, Interoperable, Reusable — the data principles behind FAIRsharing and the Blueprint |
| **Registry record** | One FAIRsharing entry, with an identifier (`FAIRsharing.xxxxxx`), a DOI, a record type, a status and subject terms |
| **Direct record lookup** | Requesting JSON at a FAIRsharing record's own URL. Needs no account, cannot search. Used for identifiers we already hold and for checking a record still resolves |
| **REST API** | FAIRsharing's `api.fairsharing.org`. Needs an account. Our fallback if GraphQL proves unstable |
| **GraphQL API** | FAIRsharing's query API, described by them as still in development. Needs a key. The expected route for live searching |
| **OAI-PMH** | Open Archives Initiative Protocol for Metadata Harvesting — FAIRsharing's bulk-harvest endpoint, described as work in progress |
| **MCP** | Model Context Protocol. The Blueprint refers to a FAIRsharing MCP server; one exists (Oxford Competency Centers, 97 tools over GraphQL). Treated as a *reference* for writing queries, not a dependency — an MCP server exists so a model can choose a tool, and §5.6 says our model chooses nothing |
| **FigShare / Zenodo** | General-purpose public repositories, used only as a source of test deposits. Never a live dependency |
| **Deposit** | One published dataset in such a repository, identified by DOI |
| **RDM** | Research Data Management. "The Library RDM team" is the referral target for abstentions |
| **RSE** | Research Software Engineer(ing) |

## Named standards and formats

| Acronym | Expansion / use here |
|---|---|
| **ISO 8601** | Date and time representation. The R3.4 recommendation for any column recognised as dates |
| **ISO 6709** | Geographic point coordinates |
| **ISO 3166** | Country codes |
| **ISO 639** | Language codes |
| **UCUM** | Unified Code for Units of Measure |
| **OWL** | Web Ontology Language. In the §1.2 fallback, indicates an ontology |
| **SKOS** | Simple Knowledge Organization System. Indicates a controlled vocabulary |
| **OBO** | Open Biological and Biomedical Ontologies format. Also treated as indicating a vocabulary in that fallback |
| **PROV-O** | The W3C provenance ontology. One PROV-O graph per run satisfies C12 (§6.3) |
| **JSON** | The interchange format for everything entering and leaving the pipeline |
| **JSON Schema** | The definitive form of the output contracts in §6; the examples there are illustrative |
| **JSON-LD** | The serialisation of the per-run provenance graph (`prov.jsonld`) |
| **CSV / Parquet / XLSX / NetCDF** | Tabular and scientific file formats, used in §2 as R3.3 examples |
| **DOI** | Digital Object Identifier. Carried by every recommendation, both as attribution and as a resolvability check |
| **URI / URN** | Uniform Resource Identifier / Name. Concept identifiers are URIs; the agent identity is a URN (`urn:dd:agent:sheffield-r3`) |
| **ORCID** | Researcher identifier. Relevant only because an ORCID sign-in to FAIRsharing must also set a password |
| **NCBI Taxonomy** | The organism vocabulary used as the worked example in §6.2 |
| **CC-BY-SA 4.0** | The licence on FAIRsharing content. Share-alike bites on redistribution, hence §7.4's recommendation to publish record identifiers only |
| **WCAG 2.1** | Web Content Accessibility Guidelines. Control C6, deliberately out of scope at v0.1 and stated on screen rather than left unsaid |
