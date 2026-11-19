# The Data Management Plan Checker evaluation

An evaluation of `advisor.dmp` on Inspect AI
([Evaluation and conformance](../../../../../docs/specs/evaluation.md)): how well it reads the
sharing commitments of a free-text plan the researcher attached, and whether it flags what the
commitments a researcher confirmed differ from what is now planned (#962). Every case goes through
the harness's conductor, so the policy gate, the input check and the grounding linter run as they
do in any other invocation.

```bash
uv run inspect eval agents/advisor-dmp/src/dd_agent_advisor_dmp/evals/reading.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/advisor-dmp/src/dd_agent_advisor_dmp/evals/reading.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
```

`--model none` is right: Inspect calls no model. The checker's own variables choose what is
evaluated (`DD_DMP_MATCHER`, `DD_MODEL_PROVIDER`, `DD_MODEL_ID`), and the log records them. The
evaluation's default is the template path, although the checker's is a model. CI runs the
template path, on which a plan is not read, so the reading cases expect the checker to say so.

## The cases

Three plans in `data/`, written for this evaluation, so that their commitments are known by
construction (`cases.yaml` labels each, with the passage it rests on):

- **complete**: three outputs, each with a repository, access and licence, one under a 12-month
  embargo and one deposited in two places.
- **partial**: three outputs, some with no repository or licence stated, and audio recordings the
  plan says will not be shared: proposing them is a wrong commitment.
- **vague**: "data will be shared where appropriate", which names no output.

Each plan has a `read-*` case: the plan attached, nothing confirmed. The complete and partial
plans also have a `compare-*` case: the labelled commitments confirmed by the researcher, the
partial plan's with two corrections, and planned outputs that differ in named ways.

## Scores

Scores are kept separate; none is blended with another. A scorer that does not apply to a case
is left out of its mean.

| Scorer | Applies to | Question |
|---|---|---|
| `outcome_matches` | every case | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | every case | Did the checker stop exactly when it should have? |
| `grounding_passed` | every case | Did the grounding linter pass the run? |
| `outputs_recalled` | a plan read, with labels | What share of the labelled commitments were proposed, by name or alias? |
| `aspects_agree` | a plan read, a labelled commitment proposed | What share of their repository, access and licence values agree with the labels, a value the plan does not state counting only if left empty? |
| `no_unlabelled_commitment` | a plan read | Was nothing proposed that the plan does not commit to? |
| `quotes_found` | a plan read | Is every proposed commitment's quote in the plan it names? |
| `discrepancies_match` | a comparison | Are exactly the expected (output, aspect) differences flagged? |

`tests/test_dmp_evals.py` also runs the evaluation with a fake model, which reads each plan as
labelled. It shows that the reading scorers apply, that `no_unlabelled_commitment` catches the
audio recordings read as a commitment, and that a quote the plan does not hold never reaches the
researcher, since the checker drops it.

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it (the git
revision, the configuration, the checker's version, and the hashes of `cases.yaml`, the reading
prompt and the plans). `tests/test_dmp_evals.py` reruns the evaluation and fails on any
difference from it, better or worse. To accept a change in the checker's behaviour:

```bash
uv run inspect eval agents/advisor-dmp/src/dd_agent_advisor_dmp/evals/reading.py --model none --log-dir /tmp/dmp
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-dmp/src/dd_agent_advisor_dmp/evals/baseline.json /tmp/dmp
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-dmp/src/dd_agent_advisor_dmp/evals/baseline.json /tmp/dmp
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## What the first baseline shows

On the template path every case gets the right outcome, stops when it should and passes the
linter. Each reading case declines to read, as it should without a model, and each comparison
flags exactly the expected differences, including the one a researcher's correction leaves.

## Limits

- **The template path in CI.** Without a model the reading scorers do not apply in the committed
  baseline, so how well a model reads a plan is not measured there. The fake-model test shows only
  that the scorers work. Running it with a model and committing those results is a follow-up.
- **Synthetic plans.** Three short plans written for this evaluation, with their commitments in
  one section each. Real plans are longer and less regular. No researcher or data steward has
  reviewed the labels.
- **Lenient value matching.** A value read agrees with a label if it contains it or a form the
  label accepts, so a value with extra, wrong detail can still agree.
- **Machine-actionable plans.** The set of RDA DMP Common Standard plans is TODO(#701).
