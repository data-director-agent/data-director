# advisor.dmp

**Alpha** (`0.4.0a1`). It describes a project before its data are collected, proposing what the
researcher said and, with a model, what an attached proposal or award letter says, as project
facts for the researcher to confirm ([Describing the project](#describing-the-project)). With a
model, it reviews a plan the researcher attached against the core
requirements of a plan, good practice and the decisions made in the project. It compares the commitments it is given or a
researcher confirmed, and with a model reads a free-text plan the researcher attached to propose
them (#962). Reading a machine-actionable plan itself is TODO(#701).

The Data Management Planner is one persona of the agent roster ([Agents](../../docs/specs/agents.md)). It serves three
steps of the process flow:

| Step | What it does |
|---|---|
| `setup.project` | Proposes what the project is for, its field of study, when it runs and the data it will produce, as project facts for the researcher to confirm, and says what is still needed ([Describing the project](#describing-the-project)). Our addition to the Blueprint's Figure 1. |
| `setup.dmp-review` | Has a model review the plan attached against Science Europe's core requirements, UKRI and UK Data Service good practice and the decisions made in the project ([Reviewing a plan](#reviewing-a-plan)). |
| `governance.dmp` (R8) | Compares what the data management plan committed to share with what is planned at publication, and lists each difference for a person to review. |

Writing a plan (`setup.dmp-create`) is the Documentation Editor's: a written plan is a project
document, the core `Document`, and this checker's payload is its own.

R8 asks that sharing at publication be checked against the plan's commitments, with
discrepancies flagged for human review and never enforced. A reviewed decision not to share is a
valid outcome, and the checker says so.

## Describing the project

Phase 1 opens with "Describe your project" (`setup.project`), since every later planning step
builds on what the project is and the data it will produce. `ProjectDescriptionRequest` carries
what the researcher said, each optional: `research_summary`, `field_of_study`, `period_start` and
`period_end`. What they say of their data the orchestrator proposes itself, as a `data_description`
(#1507). In a project the conductor also gives the attached documents and the decided facts.

The Planner proposes what the researcher said first, as `project_summary`, `field_of_study` and
`project_period` facts. With a model (`describe.py`, `describe_prompt.md`), it
reads the attached documents for what they did not say, a `data_description` among it; each thing read must quote the document it
names, and is dropped and said otherwise (`read_plan.unquoted`), as a plan's commitments are. It
never proposes a fact a person has already decided. The payload's `still_needed` names what neither
gives, for the orchestrator to ask. Nothing counts until a person decides it, and the step is done
once a person decides what the project is for. The Documentation Editor then places what was
decided in the README that plans the documentation and in a Data Management Plan.

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
with `insufficient_input`. The payload's `section_findings` say what it found.

There is no rule behind the review. A plan's headings say little about whether it answers a
requirement, and a decision's wording may differ from the plan's, so a review by rule could not
tell a good plan from a poor one. A model reads the plan (`review_model.py`), and code checks each
reading before it is used. With `DD_DMP_MATCHER=template`, which turns the model off, the checker
abstains with `capability_not_implemented` and says why.

The model is given the plan (its first 60,000 characters), each of Science Europe's six core
requirements with its questions, and the decisions people in the project made: the funder, a
required repository, a licence, a standard, and any sensitive data identified. Its system prompt
(`review_prompt.md`) sets out what a good plan looks like, from the
[STFC/UKRI](https://www.ukri.org/councils/stfc/guidance-for-applicants/what-to-include-in-your-proposal/data-management-plan/)
and [UK Data Service](https://ukdataservice.ac.uk/learning-hub/data-producer-support/planning-and-governing-research-data/planning/data-management-planning/)
guidance. A plan is:

- **specific and justified**: concrete decisions and reasons, not generic statements;
- **proportionate**: its effort matches the value and complexity of the data;
- **clear on the essentials**: repositories, metadata and documentation, the software needed to
  read the data, retention and persistent identifiers are stated;
- **realistic**: staff, training, computing and costs are identified and justified;
- **transparent**: restrictions on sharing and any embargo are explained, not hidden;
- **owned**: roles and responsibilities go to named people or teams;
- **maintained**: it says how it will be reviewed and updated as the research proceeds;
- **FAIR-oriented**: a sharing strategy for the end of the project is planned from the start.

UK funders' typical specifics (original data kept for at least ten years, published data public
within about six months unless an embargo is justified, an established repository) are put to the
model as good practice, not as a rule for every project.

For each requirement the model says how fully the plan answers it, quotes the plan's words, and
gives a reason, which also says where a decision made in the project is not reflected. A reading is
used only if it names a requirement it was given, once, gives a reason, and, where it says the plan
answers the requirement wholly or in part, quotes words found in the plan (case, whitespace,
quotation marks and dashes set aside). Its answer becomes the finding: `fully` is `covered`,
`partly` is `vague` and `not` is `missing`. A reading that fails a check is listed in `dropped`,
and its requirement has no finding. If the model cannot be reached, declines, replies outside the
schema or no reading is usable, the checker abstains and the statement says why.

The review never changes the plan, and says nothing of whether it meets a funder's own template.

## Evaluation

[`evals/`](src/dd_agent_advisor_dmp/evals/README.md) reads a complete, a partial and a vague
synthetic plan, and compares the commitments a researcher confirmed, against a committed
baseline.

## Settings

| Setting | Values |
|---|---|
| `DD_DMP_MATCHER` | `model` (default): a model reviews and reads an attached plan and reads what the rules leave over (`anthropic` names the same with the Anthropic provider); with no key and no broker credential the agent stops at start-up and says to set `template`. `template`: rules only, no model, no key. The model and its key are set as for every agent ([AI models](../../docs/guide/operations/ai-models.md)). |

## Run it

```sh
uv run dd-advisor-dmp serve --port 8112
uv run workbench invoke --agent advisor.dmp --input workbench/samples/dmp-commitments.json
uv run pytest agents/advisor-dmp
```

Without a model key, set `DD_DMP_MATCHER=template` first; it compares commitments by rule and reviews no plan.

## What it does not do

- Its review reads one funder-neutral template. A funder's own template (UKRI's councils',
  Horizon Europe's) asks for more; choosing one by the institutional profile is a follow-up.
- Its review needs a model: on the template path there is none. A model's reading may be wrong, and
  a quote found in the plan does not make it right.
- Its review has no evaluation set yet: how often the model misjudges a plan is not measured.

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
