# The repository advisor evaluation

An evaluation of `advisor.repository` on Inspect AI
([Evaluation and conformance](../../../../../docs/specs/evaluation.md)): whether the repositories a
confirmed data management plan names reach the researcher as the plan's, beside the shortlist or
without one (#1334), and whether a researcher's own institution's repository is offered when
re3data does not list it (#1342). Every case goes through the harness's conductor, so the policy gate, the
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

Real repositories and institutions only (#1342). Durham University's data repository ("Durham
University Repositories", DataCite `bl.durham`) and the British Library Research Repository
(DataCite `bl.repo`) mint DataCite DOIs, and re3data lists neither, as it does not list many an
institution's own repository. The University of York's is in re3data. `cases.yaml` gives the
source and each case:

- **Durham, no plan**: a Durham researcher's shortlist offers the university's repository beside
  the rest, from DataCite's record, matched by the ROR of its DataCite member.
- **York, no plan**: a researcher of another institution is not offered it: it takes deposits
  from Durham's members.
- **Durham, plan confirmed**: one confirmed commitment per destination, each with the repository
  in its subject, as the plan checker reads one sentence that names both. Both are offered as the
  plan's, and can be chosen.
- **plan without a shortlist**: the confirmed commitments and nothing to search for. A succeeded
  payload must rest on a record retrieved (grounding rule G2); DataCite's records are retrieved,
  so the plan's repositories are described, where before #1342 the advisor could only name them
  and stop.

## Scores

Scores are kept separate; none is blended with another. A scorer that does not apply to a case
is left out of its mean.

| Scorer | Applies to | Question |
|---|---|---|
| `outcome_matches` | every case | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | every case | Did the advisor stop exactly when it should have? |
| `grounding_passed` | every case | Did the grounding linter pass the run? |
| `plan_repositories_shown` | a confirmed plan | What share of the repositories the plan names, by registry identifier, are offered as the plan's, to be chosen? |
| `institution_repository_offered` | a case that names an institution's repository | What share hold of: each repository of the researcher's institution is offered, and none of another's? |
| `shortlist_kept` | a case with something to search for | Is a repository still recommended beside what the plan names? |

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it (the git
revision, the configuration, the advisor's version, and the hashes of `cases.yaml`, the ranking
rules, the list of other names for repositories, the pinned re3data registry and the DataCite
snapshot).
`tests/test_repository_evals.py` reruns the evaluation and fails on any difference from it,
better or worse. To accept a change in the advisor's behaviour:

```bash
uv run inspect eval agents/advisor-repository/src/dd_agent_advisor_repository/evals/shortlist.py --model none --log-dir /tmp/repository
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-repository/src/dd_agent_advisor_repository/evals/baseline.json /tmp/repository
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-repository/src/dd_agent_advisor_repository/evals/baseline.json /tmp/repository
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## Limits

- **Few cases.** The cases test two failures, the plan's repositories and the researcher's own
  institution's, on one project. They do not measure whether a shortlist is a good one: that
  needs a domain expert's labels.
- **The profile.** The cases run under the test profile, which names no repository of its own, so
  what a deployment vouches for is tested in `tests/test_repository_datacite.py`, not here.
