# advisor.dmp

**Alpha** (`0.2.0a1`). It compares the commitments it is given or a researcher confirmed, and with
a model reads a free-text plan the researcher attached to propose them (#962). Reading a
machine-actionable plan itself is TODO(#701).

The Data Management Plan Checker is one persona of the agent roster ([Agents](../../docs/specs/agents.md)). It serves one
step of the Blueprint's process flow:

| Step | What it does |
|---|---|
| `governance.dmp` (R8) | Compares what the data management plan committed to share with what is planned at publication, and lists each difference for a person to review. |

R8 asks that sharing at publication be checked against the plan's commitments, with
discrepancies flagged for human review and never enforced. A reviewed decision not to share is a
valid outcome, and the checker says so.

## Input and output

`DmpCommitments` gives the plan's identifier, if any, and two lists of `SharingCommitment`:
`committed_outputs` (what the plan committed to) and `planned_outputs` (what is planned now).
Each names an `output` and may give its `repository`, `access` (such as open, restricted or
closed) and `licence`.

`DmpDiscrepancies` holds:

- `discrepancies`, each with the `output`, the `aspect` that differs (`missing`, `unplanned`,
  `renamed`, `repository`, `access` or `licence`), what was `committed` and `planned`, a
  `message`, how it was found (`discrepancy_derivation`: `lexical` by rule, `model` for a
  renamed output) and, for a model's, its `reason`;
- `reconciled`, differences a model judged to be two names for one thing, each with its
  `reason`, shown so a person can overrule them;
- `dropped`, what the model proposed that was not used, and why;
- `limitations`, what the checker does not do.

## How it decides

Rules first:

- Outputs are matched by name, case and surrounding spaces ignored.
- An output committed but not planned is `missing`; one planned but not committed is
  `unplanned`.
- For an output on both lists, `repository`, `access` and `licence` are compared as text where
  both sides give them, and each difference is listed.
- It abstains with `insufficient_input` when no committed outputs are given and no plan is
  attached.

Then, with the matcher model on (the default; `DD_DMP_MATCHER=template` turns it off), the model is given only what the
rules left over: the missing and unplanned outputs, and the differing values. Nothing the rules
matched exactly is sent, nor the plan's identifier. It may propose:

- **a pairing**: a missing output that is planned under another name. The two flags become one
  `renamed` flag, with the model's reason, still for review; the paired outputs' repository,
  access and licence are then compared by rule.
- **an equivalence**: two values of one aspect that name the same thing, such as `CC-BY` and
  `CC BY 4.0`. The difference moves from `discrepancies` to `reconciled`, with the reason.

The model never removes a flag from what the person reviewing sees. A pairing or equivalence
naming an output or value not in the input, a second pairing for one output, or one with no
reason is dropped and listed in `dropped`. A refusal, a reply that is not the schema's JSON, or
a model that cannot be reached leaves the rules' result, and the outcome statement says why.

It reads only its input, so its grounding mode is `input_only` and it cites only its input.

## Reading an attached plan

In a project the conductor also gives the checker the documents the researcher attached and the
facts people decided. Where no commitment is typed or confirmed but a plan is attached, the model
reads the plan (`read_plan.py`) and the checker proposes each commitment it finds, with the
passage it rests on, as a `sharing_commitment` fact for the researcher to confirm, correct or
reject. A commitment whose quote is not in the plan is dropped and said. It compares nothing until
the researcher has decided, and then only what they confirmed, as they corrected it. "No
commitment found" and "too vague to say" are results, not failures. On the template path a plan
is not read: the checker abstains with `capability_not_implemented` and asks for the outputs the
plan committed to share. If the model cannot be reached or its reply is unusable, the outcome is
`succeeded` with no proposals and its statement says why. Only the start of the attached text
(60,000 characters, the latest document first) is read.

## Evaluation

[`evals/`](src/dd_agent_advisor_dmp/evals/README.md) reads a complete, a partial and a vague
synthetic plan, and compares the commitments a researcher confirmed, against a committed
baseline.

## Settings

| Setting | Values |
|---|---|
| `DD_DMP_MATCHER` | `model` (default): a model reads what the rules leave over (`anthropic` names the same with the Anthropic provider); with no key and no broker credential the agent stops at start-up and says to set `template`. `template`: rules only, no model, no key. The model and its key are set as for every agent ([AI models](../../docs/guide/operations/ai-models.md)). |

## Run it

```sh
uv run dd-advisor-dmp serve --port 8112
uv run workbench invoke --agent advisor.dmp --input workbench/samples/dmp-commitments.json
uv run pytest agents/advisor-dmp
```

Without a model key, set `DD_DMP_MATCHER=template` first.

## What it does not do

- It reads a free-text plan only with a model, and only to propose commitments for the researcher
  to confirm. It does not yet read a machine-actionable plan in the RDA DMP Common Standard by
  its identifier (see #284). TODO(#701)
- On the template path, an output renamed since the plan is reported as both missing and
  unplanned, and two names for the same repository or licence count as different.
- A pairing or reconciliation is a model's reading of names, not a check of the plan.
- It does not check timing, embargoes, costs, metadata standards or any other commitment.
- Its evaluation ([`evals/`](src/dd_agent_advisor_dmp/evals/README.md)) has three synthetic
  plans, and its committed baseline is the template path's, so neither how well a model reads
  real plans nor how often the matcher misses a renamed output is measured yet. It stays alpha.
