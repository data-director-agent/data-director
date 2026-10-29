# The standards advisor evaluation

A seeded-defect evaluation of `advisor.standards` on Inspect AI
([ADR-0013](../../../../../docs/adr/0013-evaluation.md)). Each case takes the
soil-chemistry sample profile, breaks it in one registered way (`defects.py`), and states what the standards advisor
should then do (`cases.yaml`). Every case goes through the workbench conductor, so the policy
gate, the input check and the grounding linter run as they do in any other invocation.

```bash
uv run inspect eval agents/advisor-standards/src/dd_agent_advisor_standards/evals/seeded.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/advisor-standards/src/dd_agent_advisor_standards/evals/seeded.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
uv run python workbench/scripts/eval_compare.py logs/OLD.eval logs/NEW.eval
```

`--model none` is correct: the evaluation calls no model. The standards advisor's own environment variables
(`DD_STANDARDS_EXPLAINER`, `DD_STANDARDS_RETRIEVAL`, …) choose what is evaluated, and the log records them.

## Scores

Scores are kept separate; none is blended with another.

| Scorer | Question |
|---|---|
| `outcome_matches` | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | Did the standards advisor stop exactly when it should have? The two ways of being wrong are counted separately; a `failed` run counts as neither. |
| `grounding_passed` | Did the grounding linter pass the run? |
| `expected_recall` | What share of the expected records and kinds did the standards advisor recommend? Does not apply to a case that expects none. |
| `no_wrong_recommendations` | Did the standards advisor recommend nothing labelled wrong, nothing of a kind the case rules out, and nothing deprecated? |

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it (the git
revision, the configuration, and the hashes of `ranking.yaml`, the snapshot and `cases.yaml`).
`agents/advisor-standards/tests/test_standards_evals.py` runs the evaluation and fails on any difference from it,
better or worse. To accept a change in the standards advisor's behaviour:

```bash
uv run inspect eval agents/advisor-standards/src/dd_agent_advisor_standards/evals/seeded.py --model none --log-dir /tmp/standards
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-standards/src/dd_agent_advisor_standards/evals/baseline.json /tmp/standards
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-standards/src/dd_agent_advisor_standards/evals/baseline.json /tmp/standards
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
- **Seeded defects test only faults we introduced ourselves.** They do not show how the standards advisor does on
  real deposits. A labelled corpus of ORDA (Figshare) records is
  [issue #22](https://github.com/data-director-agent/data-director/issues/22).
- **One base profile.** Every case derives from the soil-chemistry sample.
