# advisor.ethics

**Alpha** (`0.1.0a3`): a model-backed alpha ([Agents](../../docs/specs/agents.md), invariant 14).
It matches field names against a keyword table, and by default a model reads the names as well;
an operator can turn the model off with `DD_ETHICS_READER=template`. It has no evaluation set yet,
so nothing here claims it is validated.

The Research Ethics Adviser is one of the personas of the agent roster ([Agents](../../docs/specs/agents.md)). It serves two
steps of the Blueprint's process flow:

| Step | What it does |
|---|---|
| `governance.sensitive-data-identify` (identify sensitive data) | Flags each field whose name suggests personal or otherwise sensitive data, and asks the researcher to confirm consent and ethics approval when the data involve people. |
| `governance.embargo` (confirm whether an embargo is required) | Asks whether an embargo is needed, or asks the researcher to check an intended one against their policies. |

It flags and stops there. How sensitive data is treated, `governance.sensitive-data-handle`, is a
person's decision, and no agent serves it ([Agents](../../docs/specs/agents.md), C2). The adviser never suggests
anonymisation, and its model is told never to.

## Input and output

`SensitivityContext` gives the dataset's `title`, `description` and `fields` (field or column
names), and whether it `involves_people` and whether an embargo is intended
(`embargo_intended`). In a project, the conductor also fills `project_file_inventory` with the
project's inventory (it mixes in `GivenProjectInventory`, [Projects](../../docs/specs/projects.md),
invariant 6, #1540); outside one, a caller may send an inventory there. Each is optional, but a
context with no fields, no inventory and no `involves_people` abstains with `INSUFFICIENT_INPUT`,
before any model is called.

`SensitivityFlags` holds:

- `flags`: one `SensitivityFlag` per flagged field, file or folder name, with its `category`
  (direct identifier, indirect identifier, special category, location), the inventory's `files`
  it appears in, and its `derivation`: `lexical` with the keyword `matched`, or `model` with the
  model's short `reason`;
- `inventory_findings`: what the inventory's personal data detector found, copied as it is. It is
  absent when there is no inventory or its detector did not run, and empty when it ran and found
  nothing, which does not mean there is nothing;
- `questions`: what the researcher must answer or confirm, and with whom, each with its
  `derivation`: `template` for the adviser's own questions, `model` for one a model added. A
  question about consent also lists `data_use_terms`: data use conditions from the GA4GH Data
  Use Ontology (DUO), each with its identifier, shorthand, label, kind (permission or modifier)
  and IRI;
- `limitations`: what the adviser does not do;
- `dropped`: what a model returned that was not used, and why.

## How it decides

1. The names to check are the caller's `fields`, then each inventory table's field names and each
   file and folder name the inventory lists, each once (`names.py`). Each is split into words and
   matched against `keywords.yaml`. A name that matches is flagged `lexical`.
2. The reader then reads the names. With the `template` reader it adds nothing. With the
   default `model` reader a model is given the field names, the two context flags, the categories and the
   fields already flagged, and replies against a schema with further flags and at most three
   questions (`reader.py`, `system_prompt.md`).
3. A checker drops a model flag that names a field not in the input or a category not in the
   table, and records why in `dropped` and the outcome's statement.
4. **Union only.** Every keyword flag is kept as it is. A model may add a flag for a field the
   keywords missed; it cannot remove, or change the category of, a keyword flag, because a missed
   field is the costlier mistake.
5. If the model declines, replies with something that does not match the schema, or cannot be
   reached, the keyword flags stand and the statement says why.
6. When it asks about consent, it lists the DUO conditions to check that consent against: every
   permission, and the modifiers consent forms most often state (`CONSENT_MODIFIERS` in
   `agent.py`), from the release that `dd-duo` pins (`duo/`). The researcher, with their ethics
   staff, says which apply. The adviser chooses none, and the same codes are meant for access
   options (TODO(#359)).
7. With an inventory, the detector's findings are carried over and raise a question for a
   person, and a file whose name suggests free text (`dd_sdk.inventory_hints`) is named for a
   person to read. The limitations say whether the detector ran. Without an inventory they say
   that one would check more.

The adviser reads no data values and cites only its input, so its grounding mode is `input_only`.
The DUO terms are packaged vocabulary, like the keyword table, not a record retrieved for the run.
Each call is recorded with its prompt (`model_calls`), and with the `model` reader the card
declares the model (`AgentSpec.models`).

## Reader

`DD_ETHICS_READER` (`factory.py`, `config/examples/agents.env`):

- `model` (default): a model reads the names as well; `anthropic` is its older name. The model and its
  provider come from `DD_MODEL_PROVIDER`, `DD_MODEL_ID` and `DD_MODEL_BASE_URL`, with the key in
  the agent's own file ([AI models](../../docs/guide/operations/ai-models.md)). Install the
  package's `model` extra. With no key and no broker credential the agent stops at start-up and
  says to set `template`.
- `template`: keyword table only; needs no key, calls no model.

## Where field names go

With the `model` reader, which is the default, the field names a caller sends go to the configured model. A hosted model
is outside the institution, and field names of a sensitive dataset can themselves say something
about the people in it.

The profile's `hosted_models` rule ([Projects](../../docs/specs/projects.md), invariant 8)
covers `project_file_inventory`, which the conductor fills and classes as `inventory`, as it does
any agent's inventory. It does not cover `fields`, which the caller writes. Refusing caller
content to a hosted model is TODO(#40). The model is sent names only, never a file's path, a
finding or a value.

To keep the names in the institution, run the `model` reader against a local model
(`DD_MODEL_PROVIDER=openai-compatible` with a loopback `DD_MODEL_BASE_URL`), which the card then
declares `local`. Detecting personal data before anything is sent is TODO(#39).

## What it does not do

- It reads names, not values: a field it does not flag may still hold sensitive data. Only the
  inventory's detector, on the researcher's computer, looks at values and small text files.
- It does not check free text, images or audio itself, or combinations of fields that together
  identify people.
- It does not know the participants' consent, the ethics approval or the applicable law. It lists
  DUO conditions for consent to be checked against, not the ones that apply.
- It has no evaluation set yet. `tests/cases/false_negatives.json` lists field names the keyword
  table misses, the seed of the false-negative cases the persona needs before it leaves alpha
  (TODO(#700)).

The full persona, with policy records as a source, is TODO(#700) under TODO(#355).

## Run it

```sh
DD_ETHICS_READER=template uv run dd-advisor-ethics serve --port 8111   # without a model
uv run dd-advisor-ethics serve --port 8111                              # model reader, needs a key
uv run workbench invoke --agent advisor.ethics --input workbench/samples/ethics-context.json
uv run pytest agents/advisor-ethics
```

## Dependencies

`data-director-sdk` for the contract, `dd-duo` for the GA4GH Data Use Ontology's terms (CC BY 4.0,
pinned in `duo/`), Pydantic and PyYAML; with the `model` extra, the SDK's model adapters.
