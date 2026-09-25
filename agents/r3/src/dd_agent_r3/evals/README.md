# R3 evaluation

A seeded-defect evaluation of `r3.standards-advisor` on Inspect AI
([ADR-0013](../../../../../workbench/docs/adr/0013-evaluation.md)). Each case takes the
soil-chemistry sample profile, breaks it in one registered way (`defects.py`), and states what R3
should then do (`cases.yaml`). Every case goes through the workbench conductor, so the policy
gate, the input check and the grounding linter run as they do in any other invocation.

```bash
uv run inspect eval agents/r3/src/dd_agent_r3/evals/seeded.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/r3/src/dd_agent_r3/evals/seeded.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
uv run python workbench/scripts/eval_compare.py logs/OLD.eval logs/NEW.eval
```

`--model none` is correct: the evaluation calls no model. R3's own environment variables
(`DD_R3_EXPLAINER`, `DD_R3_RETRIEVAL`, …) choose what is evaluated, and the log records them.

## Scores

Scores are kept separate; none is blended with another.

| Scorer | Question |
|---|---|
| `outcome_matches` | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | Did R3 stop exactly when it should have? The two ways of being wrong are counted separately; a `failed` run counts as neither. |
| `grounding_passed` | Did the grounding linter pass the run? |
| `expected_recall` | What share of the expected records and kinds did R3 recommend? Does not apply to a case that expects none. |
| `no_wrong_recommendations` | Did R3 recommend nothing labelled wrong, nothing of a kind the case rules out, and nothing deprecated? |

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it (the git
revision, the configuration, and the hashes of `ranking.yaml`, the snapshot and `cases.yaml`).
`agents/r3/tests/test_r3_evals.py` runs the evaluation and fails on any difference from it,
better or worse. To accept a change in R3's behaviour:

```bash
uv run inspect eval agents/r3/src/dd_agent_r3/evals/seeded.py --model none --log-dir /tmp/r3
uv run python workbench/scripts/eval_compare.py --baseline agents/r3/src/dd_agent_r3/evals/baseline.json /tmp/r3
uv run python workbench/scripts/eval_compare.py --write-baseline agents/r3/src/dd_agent_r3/evals/baseline.json /tmp/r3
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## What the first baseline shows

All eight cases get the right outcome, stop when they should, and pass the linter. The subject
recommendations are weaker:

- ENVO (`FAIRsharing.azqskx`) is in the snapshot but is never recommended.
- AGROVOC (`FAIRsharing.anpj91`) is recommended only when the title is replaced with
  "Dataset 1". The title's words appear to crowd it out of the ranking.
- The Food Ontology (`FAIRsharing.dzxae`) is recommended for the soil survey.

## Limits

- **The labels are provisional.** They apply the guidance in Uzwyshyn, *The Research Data
  Director* v0.8.2 (see the header of `cases.yaml`), and no domain expert has reviewed them.
- **Seeded defects test only faults we introduced ourselves.** They do not show how R3 does on
  real deposits. A labelled corpus of ORDA (Figshare) records is
  [issue #22](https://github.com/data-director-agent/data-director/issues/22).
- **One base profile.** Every case derives from the soil-chemistry sample.
