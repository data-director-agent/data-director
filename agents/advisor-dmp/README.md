# advisor.dmp

**Alpha** (`0.3.0a1`). It reviews a plan the researcher attached against the core requirements of
a plan and the decisions made in the project. It compares the commitments it is given or a
researcher confirmed, and with a model reads a free-text plan the researcher attached to propose
them (#962). Reading a machine-actionable plan itself is TODO(#701).

The Data Management Plan Checker is one persona of the agent roster ([Agents](../../docs/specs/agents.md)). It serves two
steps of the Blueprint's process flow:

| Step | What it does |
|---|---|
| `setup.dmp-review` | Reviews the plan attached against Science Europe's core requirements and the decisions made in the project ([Reviewing a plan](#reviewing-a-plan)). |
| `governance.dmp` (R8) | Compares what the data management plan committed to share with what is planned at publication, and lists each difference for a person to review. |

Writing a plan (`setup.dmp-create`) is the Documentation Editor's: a written plan is a project
document, the core `Document`, and this checker's payload is its own.

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
facts people decided. Where a person has marked one document as the project's plan
(`documentation_is_plan`, docs/specs/projects.md, invariant 32), only that document is read; where
none is marked, every document is read and the checker also proposes the document it read the
commitments from as the plan (a `data_management_plan` fact), for a person to confirm (#1447). Where no commitment is typed or confirmed but a plan is attached, the model
reads the plan (`read_plan.py`) and the checker proposes each commitment it finds, with the
passage it rests on, as a `sharing_commitment` fact for the researcher to confirm, correct or
reject. A commitment whose quote is not in the plan is dropped and said. It compares nothing until
the researcher has decided, and then only what they confirmed, as they corrected it. "No
commitment found" and "too vague to say" are results, not failures. On the template path a plan
is not read: the checker abstains with `capability_not_implemented` and asks for the outputs the
plan committed to share. If the model cannot be reached or its reply is unusable, the outcome is
`succeeded` with no proposals and its statement says why. Only the start of the attached text
(60,000 characters, the latest document first) is read.

## Reviewing a plan

`DmpReviewRequest` carries only the attached documents and the decided facts, which the conductor
fills in a project. The plan reviewed is the document a person marked as the project's plan
(#1447), or, while none is marked, the latest document attached; with none, the checker abstains
with `insufficient_input`. The payload's `section_findings` and `decision_conflicts` say
what it found (`review.py`):

- **By rule, always.** [`dd-dmp-template`](../../dmp-template/README.md) reads the plan's headings
  against the six core requirements, after Science Europe's. A requirement a heading names, with
  text under it, is `covered`, with the start of that text quoted; one whose heading has nothing
  under it is `vague`; one no heading names is `missing`. Each says what the requirement's
  questions are, for the researcher to check. `finding_derivation` is `lexical`.
- **Decisions not reflected.** A funder, required repository, licence or standard people in the
  project decided that the plan never names (case, spaces, quotation marks and dashes set aside,
  so `CC-BY-4.0` matches "CC BY 4.0"), and sensitive data where the plan has no legal and ethical
  section, are each a `DecisionConflict` for a person to review. The plan may need updating, or the
  decision may.
- **With the model** (`review_model.py`, `review_prompt.md`), on unless `DD_DMP_MATCHER=template`.
  It is given the plan (its first 60,000 characters), each requirement's questions and the rules'
  finding, and reads how fully the plan answers each. A reading is used only if it names a
  requirement it was given, once, gives a reason, and quotes words found in the plan. It may only
  raise a finding: a `covered` requirement it reads as answered only in part becomes `vague`, with
  `finding_derivation` `model` and its reason; for a `missing` one it may point to where the plan
  answers it under another heading, which stays `missing`, with the model's reason and quote, for
  a person to judge. Readings not used are listed in `dropped`. An unusable reply leaves the rules'
  review, and the statement says why.

The review never changes the plan, and says nothing of whether it meets a funder's own template.

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

- Its review reads one funder-neutral template. A funder's own template (UKRI's councils',
  Horizon Europe's) asks for more; choosing one by the institutional profile is a follow-up.
- On the template path, its review reads only headings: a plan that answers a requirement under
  another heading, or with none, is reported as missing it.
- Its review has no evaluation set yet: how often the rules or the model miss is not measured.

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
