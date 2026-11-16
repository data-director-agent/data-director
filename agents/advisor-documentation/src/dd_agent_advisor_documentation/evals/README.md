# The Documentation Editor evaluation

An evaluation of `advisor.documentation` on Inspect AI
([Evaluation and conformance](../../../../../docs/specs/evaluation.md)). Each case takes a base
request (an inventory, the chosen repository's requirements and an approved metadata record),
breaks it in one registered way (`defects.py`), asks for a README or a data dictionary, and
states what the editor should then do (`cases.yaml`). Every case goes through the harness's
conductor, so the policy gate, the input check and the grounding linter run as they do in any other
invocation.

```bash
uv run inspect eval agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/drafting.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/drafting.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
```

`--model none` is right: Inspect calls no model. The editor's own variables choose what is
evaluated (`DD_DOCUMENTATION_WRITER`, `DD_MODEL_PROVIDER`, `DD_MODEL_ID`), and the log records
them. CI runs the template path. Running it with a model configured, and committing those
results, is a follow-up: invariant 1 of the evaluation spec says an evaluation calls no model.

## The cases

- **Hallam Moor** is Dataset A of
  [data-director-agent/sample-data](https://github.com/data-director-agent/sample-data) (MIT,
  commit `e48701a`), a synthetic upland sensor network: two exports of the same loggers with
  renamed columns, a byte-identical copy, a calibration workbook, a site table and a third-party
  weather record. `data/hallam-moor.inventory.json` is what `dd-inventory` wrote for its
  `HallamMoor_loggers` folder. The gold is section 4 of its crib sheet, the workshop facilitators'
  answer key, with section 3 for definitions. The metadata record was written for this evaluation
  from the dataset's grant proposal.
- **Soil survey** is the agent's own sample (`soil-survey.readme-with-record.draft.json`, as in
  `workbench/samples`). It has no gold.

## Scores

Scores are kept separate; none is blended with another. A scorer that does not apply to a case
(a data dictionary scorer on a README, a model scorer on the template path) is left out of its
mean.

| Scorer | Applies to | Question |
|---|---|---|
| `outcome_matches` | every case | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | every case | Did the editor stop exactly when it should have? |
| `grounding_passed` | every case | Did the grounding linter pass the run? |
| `every_cell_sourced` | data dictionary | Does every value have a source from the vocabulary, with a cell filled exactly when its source is not `unknown`? |
| `no_model_value_in_cell` | data dictionary | Does every filled cell's source account for it: an `inferred` value the inventory's, a `supplied` one the inventory's description or the researcher's recorded answer? |
| `unknown_cells_asked` | data dictionary | What share of the unknown and asked-about cells are both? |
| `inferred_types_match_gold` | data dictionary with gold | What share of the types marked `inferred` agree with the crib sheet? |
| `suggestions_match_gold` | data dictionary with gold and suggestions | What share of a model's suggested definitions and units agree with the crib sheet, naming nothing that makes them confidently wrong? |
| `required_sections_present` | README | Are all the sections of `readme.yaml` there, in order? |
| `every_gap_marked_and_asked` | README | What share of the gap markers and questions match one another? |
| `expected_content_present` | README | What share of the case's expectations hold: text present, gaps asked, gaps not asked? |
| `no_unsupported_claim` | README a model wrote prose for | Does every paragraph a model wrote name only numbers, links, identifiers and code-formatted names its facts give? |
| `answers_placed_supplied` | a case with answers | What share of the researcher's answers are placed as given (marked `supplied` in a dictionary) and not asked again? |

`tests/test_documentation_evals.py` also runs the evaluation with a fake model. It shows that
the model scorers apply and that `suggestions_match_gold` catches the crib sheet's trap (`%` for
`SM`, which is in raw counts). With the editor's own guards switched off, it shows that
`no_unsupported_claim` and `no_model_value_in_cell` catch what those guards stop.

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it (the git
revision, the configuration, the editor's version, and the hashes of `cases.yaml`, `readme.yaml`
and the data files). `tests/test_documentation_evals.py` reruns the evaluation and fails on any
difference from it, better or worse. To accept a change in the editor's behaviour:

```bash
uv run inspect eval agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/drafting.py --model none --log-dir /tmp/documentation
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/baseline.json /tmp/documentation
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/baseline.json /tmp/documentation
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## What the first baseline shows

On the template path, every case gets the right outcome, stops when it should and passes the
linter. Every dictionary value has a true source, every unknown cell is asked, every README gap is
marked and asked, and every recorded answer is placed. Two weaknesses show:

- **Seven of the 27 types marked `inferred` disagree with the crib sheet**
  (`inferred_types_match_gold`, 0.74). `dd-inventory` reads phase 1's `Date` (`dd/mm/yyyy`) and
  `Time` (`HH:MM`) as `string`, phase 2's `rh` as `string` because of its `NA` values, and
  `PM25` as `any` because it starts blank. The editor marks these `inferred`, which tells the
  researcher something false that they may not think to check. This is a fault in the inventory
  (#571 is related), not in the editor's rules.
- **The grant number is left out** (`expected_content_present` on `hallam-readme`, 17 of 18).
  The record gives the award number `NE/X999999/1`, and the **Funding** part asks for "the
  funders and grant numbers", but the README places only the funder's name and does not ask for
  the number.

## Limits

- **One labelled dataset.** Only Hallam Moor has gold, and its labels are the crib sheet's: no
  domain expert has reviewed them beyond its authors. Datasets B to D of the same repository
  could be added.
- **The template path in CI.** Without a model, the model scorers (`suggestions_match_gold`,
  `no_unsupported_claim`) do not apply in the committed baseline. The fake-model test shows only
  that they work.
- **The claim check is the editor's own.** `no_unsupported_claim` applies the patterns of
  `prose.py`, so it catches an invented number or identifier, not a misleading sentence built from
  true facts.
- **Section 4 does not cover every field.** The site table and the reference weather record have
  no gold, and neither do the date and time fields' units (the crib sheet gives their formats in
  its unit column).
