# advisor.ethics

**Alpha** (`0.1.0a1`), and a **mock**: it does not yet do the Research Ethics Adviser's real work.

The Research Ethics Adviser is one of the personas of the agent roster (ADR-0033). It serves two
steps of the Blueprint's process flow:

| Step | What the mock does |
|---|---|
| `governance.sensitive-data-identify` (identify sensitive data) | Flags each field whose name suggests personal or otherwise sensitive data, and asks the researcher to confirm consent and ethics approval when the data involve people. |
| `governance.embargo` (confirm whether an embargo is required) | Asks whether an embargo is needed, or asks the researcher to check an intended one against their policies. |

It flags and stops there. How sensitive data is treated, `governance.sensitive-data-handle`, is a
person's decision, and no agent serves it (ADR-0033 decision 2, C2). The adviser never suggests
anonymisation.

## Input and output

`SensitivityContext` gives the dataset's `title`, `description` and `fields` (field or column
names), and whether it `involves_people` and whether an embargo is intended
(`embargo_intended`). Each is optional, but a context with neither fields nor
`involves_people` abstains with `INSUFFICIENT_INPUT`.

`SensitivityFlags` holds:

- `flags`: one `SensitivityFlag` per field whose name matched, with the `category` (direct
  identifier, indirect identifier, special category, location) and the keyword `matched`;
- `questions`: what the researcher must answer or confirm, and with whom;
- `limitations`: what the mock does not do.

## How it decides

Each field name is split into words and matched against `keywords.yaml`. The adviser reads no data
values, consults no source and calls no model, so its grounding mode is `none` and it cites only
its input.

## What it does not do

- It reads names, not values: a field it does not flag may still hold sensitive data.
- It does not check free text, images or audio, or combinations of fields that together identify
  people.
- It does not know the participants' consent, the ethics approval or the applicable law.

The real adviser is TODO(#355).
