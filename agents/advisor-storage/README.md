# advisor.storage

**Model-backed alpha** (`0.1.0a2`): the Storage Adviser. It serves one step of the process flow,
`setup.storage` (plan storage, backup and security during the project), which is this
repository's addition to the Blueprint's Phase 1: where data live while a project runs is the
first thing a data service asks, and one of a Data Management Plan's core requirements (Storage
and backup during the project), but no step of the Blueprint's flow asks it.

| Part | In this agent |
|---|---|
| Input | `StorageNeeds`: `expected_volume_gb`, `involves_personal_data` (`yes`, `no` or `unknown`) and `external_collaborators`, as the researcher says them. The conductor fills `institution_storage` from the deployment's profile (`GivenInstitutionStorage`) and replaces whatever a caller sent there. In a project it also fills `project_file_inventory` with the project's inventory (`GivenProjectInventory`, #1540). When no `expected_volume_gb` is given, the inventory's total file size, rounded up to whole gigabytes, is used, and the statement says this is the current size, not a forecast. |
| Payload | `StorageAdvice`: `storage_options` (each with its `storage_id`, what it `offers` and its `concerns`), `excluded_storage` (each with why), `plan_questions`, a `summary` and how it came about, and `limitations`. |
| Grounding mode | `retrieval`: each service rests on what the profile vouches for about it, cited as `institution-storage:<storage_id>` under the profile's reference, which the harness's source check resolves against the profile it loaded. |
| Outcomes | `succeeded` with advice; `abstained` (`no_candidates_retrieved`) when the profile names no storage; `referred` (`requires_human_judgement`, to a data steward) when the data involve personal data and no service named is approved for them. |
| Steps served | `setup.storage`. |

## How it decides

The rules (`rules.py`) read only what the researcher said and what the profile vouches for:

- With personal data, a service is left out unless the profile says it is `approved_for_sensitive`.
  A service the profile says nothing about on that is never taken as approved.
- Each service kept has a concern for each thing to check before choosing it: an approval the
  profile does not state when personal data are possible (`unknown`), an expected volume above
  its `allowance_gb`, no access for people outside the institution when they need it, a charge,
  and a backup the profile does not describe.
- Services with fewer concerns come first; otherwise the profile's order stands.
- Every plan is asked how many copies there are and where, how often they are backed up and
  whether a restore has been tried, who has access, and what happens at the end of the project;
  where personal data are possible, also how they are kept secure.

A summariser (`dd_sdk.summary`) then writes a short summary beside the advice. `model`, the
default, has a model write it from the findings alone, with `system_prompt.md`; `template` gives
the rules' own (`DD_STORAGE_SUMMARISER`, `config/examples/agents.env`). It cannot change a
finding.

It does not book storage, check how a service is configured, advise on anonymisation, or decide
how sensitive data are protected: that is for the institution's ethics and data protection staff
(`governance.sensitive-data-handle`, which a person decides).

## What it depends on, and what is open

It depends on `dd_sdk` alone, for the contract and the summariser. The storage services are the
deployment's own, from its profile's `institution_storage`
([Configuration](../../docs/guide/operations/configuration.md)); no public registry lists an
institution's storage. The questions follow the core requirement "Storage and backup during the
project" of Science Europe's *Practical Guide to the International Alignment of Research Data
Management* (CC BY 4.0), as `dd-dmp-template` paraphrases it. The rules are a few lines of
Python with no Data Director dependency, and could move into a library of their own if another
tool wants them. Code under the MIT licence.

## Run it

```sh
uv run dd-advisor-storage serve --port 8118
uv run pytest agents/advisor-storage
```

The classes are declared in `src/dd_agent_advisor_storage/schema/storage.yaml`; after editing it,
run `uv run dd-gen-schema agents/advisor-storage/src/dd_agent_advisor_storage/schema/storage.yaml`
and keep `classes.py` in step.
