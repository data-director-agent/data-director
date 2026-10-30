# Sample inputs

Every sample carries `schema_class`, which names its input class; the viewer lists a sample only
for agents that accept that class, and `workbench invoke` reads it to parse the document.

| File | Class | Purpose |
|---|---|---|
| `orda-record.metadata.json` | `MetadataRecord` | A minimal repository record, hand-derived from the soil-chemistry dataset, with no licence. Exercises `advisor.quality`'s succeeded path with one unmet criterion. |
| `hello.salutation.json` | `Salutation` | Whom to greet. Exercises `example.hello`, the template agent, on its succeeded path. |
| `director.message.json` | `Message` | A greeting addressed to the orchestrator. Exercises `orchestrator.stub`'s delegation to `example.hello`; needs `workbench serve`, since `invoke` issues no delegation grant. |
| `soil-chemistry.profile.json` | `DatasetProfile` | Hand-derived from a soil-chemistry dataset's metadata and that CSV's header. The standards advisor's succeeded path, including field-level (ISO 8601) recommendations. |
| `empty.profile.json` | `DatasetProfile` | No title, keywords, themes, media types or temporal fields. The standards advisor's `abstained(insufficient_input)` path. |
| `policy-context.json` | `PolicyContext` | An ESRC-funded social scientist at the University of Sheffield publishing in PLOS ONE. The policy advisor's succeeded path, with a difference between the policies flagged. |
| `repository-needs.json` | `RepositoryNeeds` | Restricted-access social science data from a University of Sheffield researcher, with no repository mandated. The repository advisor's shortlist, including the institutional repository. |
| `repository-mandated.json` | `RepositoryNeeds` | Embargoed data with the UK Data Service mandated. The repository advisor describes it rather than shortlisting. |
| `ethics-context.json` | `SensitivityContext` | Interviews and smart-meter readings from households, with a postcode, a date of birth and health conditions among the fields. The ethics adviser mock's succeeded path, with three fields flagged. |
| `soil-survey.inventory.json` | `FileInventory` | What `uv run dd-inventory inventory/tests/data/soil-survey` writes for a five-file dataset: a README, a CSV and a TSV with their fields, a PDF and a PNG identified by PRONOM signature. Exercises `advisor.files`'s succeeded path. |
| `dmp-commitments.json` | `DmpCommitments` | A plan's sharing commitments against planned outputs: one output missing, one unplanned, one access mismatch (open vs restricted) |
| `published-record.json` | `PublishedRecord` | A published dataset's metadata for the FAIR Assessor mock: a landing-page URL rather than a DOI, no related identifiers and one creator without an ORCID iD, so three of its twelve checks are not met. |
| `metadata-draft-request.json` | `MetadataDraftRequest` | A household energy dataset with title, description, creators, keywords and year, asking for DataCite. Exercises `advisor.metadata`'s succeeded path: 5 of 8 properties filled, Identifier, Publisher and ResourceType left for the researcher. |
| `documentation-request.json` | `DocumentationRequest` | Title, creators, file names and field names of a household energy dataset, for the Documentation Editor mock to draft a README outline and data dictionary from. |
| `rights-context.json` | `RightsContext` | Data that need attribution, are sensitive and include third-party content, for the Rights and Licensing Adviser mock. |
| `link-candidates.json` | `LinkCandidates` | A DOI URL, a valid ORCID iD, an ORCID iD with a bad checksum, a ROR ID and an unrecognised arXiv ID, for the Linking Adviser mock. |

```sh
uv run workbench agents
uv run workbench invoke --agent advisor.quality --input samples/orda-record.metadata.json
uv run workbench invoke --agent advisor.standards --input samples/soil-chemistry.profile.json
uv run workbench invoke --agent example.hello     --input samples/hello.salutation.json
uv run workbench invoke --agent advisor.policy --input samples/policy-context.json
uv run workbench invoke --agent advisor.repository --input samples/repository-needs.json
uv run workbench invoke --agent advisor.quality --input samples/hello.salutation.json   # failed: input-not-accepted
```
