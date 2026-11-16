# advisor.ethics

**Alpha** (`0.1.0a1`): a model-backed alpha ([Agents](../../docs/specs/agents.md), invariant 14).
By default it matches field names against a keyword table; an operator can add a model that reads
the names as well. It has no evaluation set yet, so nothing here claims it is validated.

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
(`embargo_intended`). Each is optional, but a context with neither fields nor
`involves_people` abstains with `INSUFFICIENT_INPUT`, before any model is called.

`SensitivityFlags` holds:

- `flags`: one `SensitivityFlag` per flagged field, with its `category` (direct identifier,
  indirect identifier, special category, location) and its `derivation`: `lexical` with the
  keyword `matched`, or `model` with the model's short `reason`;
- `questions`: what the researcher must answer or confirm, and with whom, each with its
  `derivation`: `template` for the adviser's own questions, `model` for one a model added;
- `limitations`: what the adviser does not do;
- `dropped`: what a model returned that was not used, and why.

## How it decides

1. Each field name is split into words and matched against `keywords.yaml`. A field that matches
   is flagged `lexical`.
2. The reader then reads the names. With the default `template` reader it adds nothing. With the
   `model` reader a model is given the field names, the two context flags, the categories and the
   fields already flagged, and replies against a schema with further flags and at most three
   questions (`reader.py`, `system_prompt.md`).
3. A checker drops a model flag that names a field not in the input or a category not in the
   table, and records why in `dropped` and the outcome's statement.
4. **Union only.** Every keyword flag is kept as it is. A model may add a flag for a field the
   keywords missed; it cannot remove, or change the category of, a keyword flag, because a missed
   field is the costlier mistake.
5. If the model declines, replies with something that does not match the schema, or cannot be
   reached, the keyword flags stand and the statement says why.

The adviser reads no data values and cites only its input, so its grounding mode is `input_only`.
Each call is recorded with its prompt (`model_calls`), and with the `model` reader the card
declares the model (`AgentSpec.models`).

## Reader

`DD_ETHICS_READER` (`factory.py`, `config/examples/agents.env`):

- `template` (default): keyword table only; needs no key, calls no model.
- `model`: a model reads the names as well; `anthropic` is its older name. The model and its
  provider come from `DD_MODEL_PROVIDER`, `DD_MODEL_ID` and `DD_MODEL_BASE_URL`, with the key in
  the agent's own file ([AI models](../../docs/guide/operations/ai-models.md)). Install the
  package's `model` extra.

## Where field names go

With the `model` reader, the field names a caller sends go to the configured model. A hosted model
is outside the institution, and field names of a sensitive dataset can themselves say something
about the people in it.

The profile's `hosted_models` rule ([Projects](../../docs/specs/projects.md), invariant 8) does
not apply to this input: it covers the project content the conductor fills (inventory,
documentation, researcher facts), and `SensitivityContext` is written by its caller, so the
conductor neither fills nor classifies it. Refusing caller content to a hosted model is
TODO(#40). Note that field names already reach hosted models by default as part of a project's
`inventory`, which `FileInventory` holds for each table.

To keep the names in the institution, run the `model` reader against a local model
(`DD_MODEL_PROVIDER=openai-compatible` with a loopback `DD_MODEL_BASE_URL`), which the card then
declares `local`. Detecting personal data before anything is sent is TODO(#39).

## What it does not do

- It reads names, not values: a field it does not flag may still hold sensitive data.
- It does not check free text, images or audio, or combinations of fields that together identify
  people.
- It does not know the participants' consent, the ethics approval or the applicable law.
- It has no evaluation set yet. `tests/cases/false_negatives.json` lists field names the keyword
  table misses, the seed of the false-negative cases the persona needs before it leaves alpha
  (TODO(#700)).

The full persona, with policy records as a source, is TODO(#700) under TODO(#355).
