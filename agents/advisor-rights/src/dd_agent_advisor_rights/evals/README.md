# The Rights and Licensing Adviser evaluation

An evaluation of `advisor.rights` on Inspect AI
([Evaluation and conformance](../../../../../docs/specs/evaluation.md)). For a reuse wish, a mandate,
sensitive data or third-party content, it asks three things. Are the licences and access levels
offered those a data steward would list, with none that do not fit? And are the questions the
researcher must be asked asked? Every case goes through the harness's conductor, so the policy
gate, the input check and the grounding linter run as they do in any other invocation (#702).

```bash
uv run inspect eval agents/advisor-rights/src/dd_agent_advisor_rights/evals/choosing.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/advisor-rights/src/dd_agent_advisor_rights/evals/choosing.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
```

`--model none` is right: Inspect calls no model. The adviser's own variables choose what is
evaluated (`DD_RIGHTS_INTERPRETER`, `DD_MODEL_PROVIDER`, `DD_MODEL_ID`), and the log records
them. The evaluation's default is the template interpreter, although the adviser's is a model.
The workbench's profile grants no `spdx` tool server, so the adviser reads its packaged table.

## The cases

`cases.yaml` holds the cases. Each case gives a `RightsContext` and what a data steward would
expect of the answer:

- **A reuse wish the rules understand** (any, attribution, share-alike, non-commercial).
  Share-alike expects CC-BY-SA-4.0 as well as ODbL-1.0. The adviser's table lacks it, so that
  case records a false negative.
- **A reuse wish in the researcher's own words**, such as "anyone may use it, but nobody may sell
  it". On the template path these are not read, and every licence is listed, so the licences that
  do not fit are counted as wrong.
- **A mandated licence**: one in the table, one outside it, and one at odds with the reuse wished
  for.
- **Sensitive data, unknown sensitivity and third-party content**: the access levels that must
  lead, and the questions that must be asked.
- **Nothing said**: the adviser must abstain (`insufficient_input`).

A missed licence, access level or question is the false negative a steward would not want: the
option the adviser must not leave out
([Agents](../../../../../docs/specs/agents.md), leaving alpha).

## Scores

Scores are kept separate; none is blended with another. A scorer that does not apply to a case is
left out of its mean.

| Scorer | Applies to | Question |
|---|---|---|
| `outcome_matches` | every case | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | every case | Did the adviser stop exactly when it should have? |
| `grounding_passed` | every case | Did the grounding linter pass the run? |
| `ids_recalled` | a case with `include` | What share of the licences a steward would list are offered? The misses are its false negatives. |
| `none_listed` | a case with `exclude` | Is no licence offered that does not fit what was asked? |
| `access_first` | a case with `access_first` | Do these access levels lead the list, in this order? |
| `questions_asked` | a case with `questions` | What share of the questions the researcher must be asked are asked? |

`ids_recalled` and `none_listed` are the workbench's (`workbench.evaluation`), so that other
agents whose payload lists options by id can use them. `access_first` and `questions_asked` are
this adviser's (`scorers.py`). A question is recognised by the adviser's own question constant,
not by wording written in the case.

`tests/test_rights_evals.py` also runs the evaluation with a fake model that reads each free-word
wish as a steward would. It shows that those cases then score in full. A second fake model misreads
"nobody may sell it" as any reuse, and the test shows the evaluation catches the licences that
follow. The closed-set check cannot catch them, since they fit the misreading.

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it: the git
revision, the configuration, the adviser's version, and the hashes of `cases.yaml`,
`licences.yaml` and `system_prompt.md`. `tests/test_rights_evals.py` reruns the evaluation and
fails on any difference from it, better or worse. To accept a change in the adviser's behaviour:

```bash
uv run inspect eval agents/advisor-rights/src/dd_agent_advisor_rights/evals/choosing.py --model none --log-dir /tmp/rights
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-rights/src/dd_agent_advisor_rights/evals/baseline.json /tmp/rights
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-rights/src/dd_agent_advisor_rights/evals/baseline.json /tmp/rights
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## Limits

- **The labels are provisional.** They follow common data-licensing guidance (Creative Commons,
  Open Data Commons, the Digital Curation Centre's *How to license research data*). No data
  steward has reviewed them yet.
- **The template path.** The baseline measures the rules. A model's reading of free words is
  measured only with the fake model, not with a real one.
- **The packaged table.** The cases run without the `spdx` tool server, so retrieval through the
  gateway is tested in `tests/test_rights_gateway.py`, not here. The repository's licence options
  and the Open Definition are not yet inputs (TODO(#702)).
