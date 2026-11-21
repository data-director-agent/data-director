# The repository advisor evaluation

An evaluation of `advisor.repository` on Inspect AI
([Evaluation and conformance](../../../../../docs/specs/evaluation.md)): whether the repositories a
confirmed data management plan names reach the researcher as the plan's, beside the shortlist or
without one (#1334). Every case goes through the harness's conductor, so the policy gate, the
input check and the grounding linter run as they do in any other invocation.

```bash
uv run dd-sources prepare                             # the pinned re3data registry, once
uv run inspect eval agents/advisor-repository/src/dd_agent_advisor_repository/evals/shortlist.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/advisor-repository/src/dd_agent_advisor_repository/evals/shortlist.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
```

`--model none` is right: Inspect calls no model. The advisor's own variables choose what is
evaluated (`DD_REPOSITORY_EXPLAINER`, `DD_REPOSITORY_RETRIEVAL`, `DD_MODEL_ID`), and the log
records them. The evaluation's default is the template explainer, although the advisor's is a
model. No model chooses a repository either way, so the scores below do not depend on it.

## The cases

Dataset F of `data-director-agent/sample-data` ("Mill Voices", an oral-history archive), whose
data management plan commits the audio masters, transcripts and image archive to the
institution's own repository and a copy to a local authority archive. Both are fictional, so
re3data lists neither, as it does not list many an institution's or a local archive's repository.
`cases.yaml` gives the source and each case:

- **plan unconfirmed**: the smoke test as run (#1325). The plan was attached but its commitments
  not confirmed, so nothing of it reaches the advisor, which shortlists from re3data alone.
- **plan confirmed**: one confirmed commitment per destination.
- **plan in one commitment**: both destinations in one commitment, as the plan's single sentence
  gives them.
- **plan without a shortlist**: the confirmed commitments and nothing to search for.

## Scores

Scores are kept separate; none is blended with another. A scorer that does not apply to a case
is left out of its mean.

| Scorer | Applies to | Question |
|---|---|---|
| `outcome_matches` | every case | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | every case | Did the advisor stop exactly when it should have? |
| `grounding_passed` | every case | Did the grounding linter pass the run? |
| `plan_repositories_shown` | a confirmed plan | What share of the repositories the plan names are shown as the plan's? |
| `shortlist_kept` | a case with something to search for | Is a repository still recommended beside what the plan names? |

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it (the git
revision, the configuration, the advisor's version, and the hashes of `cases.yaml`, the ranking
rules, the list of other names for repositories and the pinned re3data registry).
`tests/test_repository_evals.py` reruns the evaluation and fails on any difference from it,
better or worse. To accept a change in the advisor's behaviour:

```bash
uv run inspect eval agents/advisor-repository/src/dd_agent_advisor_repository/evals/shortlist.py --model none --log-dir /tmp/repository
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-repository/src/dd_agent_advisor_repository/evals/baseline.json /tmp/repository
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-repository/src/dd_agent_advisor_repository/evals/baseline.json /tmp/repository
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## Limits

- **One dataset.** The cases test one failure, the plan's repositories, on one dataset. They do
  not measure whether a shortlist is a good one: that needs a domain expert's labels.
- **The institution's own repository.** A repository the deployment names as the institution's
  is not yet a source of candidates (#320), so no case expects one.
