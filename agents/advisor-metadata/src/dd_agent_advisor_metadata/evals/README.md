# The Metadata Librarian evaluation

An evaluation of `advisor.metadata` on Inspect AI
([Evaluation and conformance](../../../../../docs/specs/evaluation.md)). For a dataset deposited
in ORDA, it asks four things:

- Are the categories suggested from the repository's controlled vocabulary those a curator would
  choose?
- Does each suggested category cite the vocabulary record it came from?
- Is the researcher asked about every value only they can give?
- Are those values left null?

Every case goes through the harness's conductor, so the policy gate, the input check and the
grounding linter run as they do in any other invocation (#703).

```bash
uv run inspect eval agents/advisor-metadata/src/dd_agent_advisor_metadata/evals/drafting.py --model none
uv run inspect view                                   # browse the logs in ./logs
uv run inspect eval agents/advisor-metadata/src/dd_agent_advisor_metadata/evals/drafting.py --model none \
    -T agents=workbench/agents.yaml                   # the deployed services instead
```

`--model none` is right: Inspect calls no model. The librarian's own variables choose what is
evaluated (`DD_METADATA_SUGGESTER`, `DD_MODEL_PROVIDER`, `DD_MODEL_ID`), and the log records them.
The evaluation's default is the template suggester, although the librarian's default is a model.

## The cases

`cases.yaml` holds the cases. Each is a small inventory, sometimes with the keywords a researcher
kept from their ORCID record, drafted against ORDA's requirements. ORDA asks for keywords and for
categories from the ANZSRC Fields of Research. The cases cover:

- environmental and earth sciences (soil, river flow, air quality, microplastics);
- life and health sciences (pollinators, RNA sequencing, a gait trial);
- physical sciences and engineering (battery cycling, a wind tunnel, simulation code);
- social sciences and humanities (interviews, a survey, parish records, a dialect corpus).

Each drafted case names the ANZSRC groups a curator would choose. Three cases must stop instead:

- a repository that asks for Dublin Core (`capability_not_implemented`: the librarian drafts
  DataCite only and maps nothing between schemas, TODO(#1363));
- no repository chosen (`insufficient_input`);
- a README asked of the librarian (`outside_agent_scope`).

A missed category is the false negative a curator would not want. A category suggested with no
record to show it is a term the researcher cannot check, so it is scored apart.

## Scores

Scores are kept separate; none is blended with another. A scorer that does not apply to a case is
left out of its mean.

| Scorer | Applies to | Question |
|---|---|---|
| `outcome_matches` | every case | Is the status (and reason code, if the case names one) the expected one? |
| `stopped_correctly` | every case | Did the librarian stop exactly when it should have? |
| `grounding_passed` | every case | Did the grounding linter pass the run? |
| `subjects_recalled` | a case with `subjects` | What share of the categories a curator would choose is suggested, by code or label? |
| `terms_cited` | a run that suggests a category | What share of the suggested categories does a retrieved record in the evidence give? |
| `questions_asked` | a case with `asked` | What share of the properties the researcher must be asked about are asked about? |
| `nothing_placed` | a case with `never_placed` | Is every value only the researcher can give left null? |

A category question is found by its `gap_property` and the `subjectScheme` qualifier on the
record's entry, not by its wording. `tests/test_metadata_evals.py` also scores a hand-made draft
that suggests categories. It shows that the two category scorers count a suggestion that a
retrieved record gives, and catch one that no record gives.

## The baseline

`baseline.json` holds the per-case scores of the accepted run and what produced it: the git
revision, the configuration, the librarian's version, and the hashes of `cases.yaml`, DataCite's
definition in `dd_metadata_records`, `shares.yaml` and `suggest_prompt.md`.
`tests/test_metadata_evals.py` reruns the evaluation and fails on any difference from it, better
or worse. To accept a change in the librarian's behaviour:

```bash
uv run inspect eval agents/advisor-metadata/src/dd_agent_advisor_metadata/evals/drafting.py --model none --log-dir /tmp/metadata
uv run python workbench/scripts/eval_compare.py --baseline agents/advisor-metadata/src/dd_agent_advisor_metadata/evals/baseline.json /tmp/metadata
uv run python workbench/scripts/eval_compare.py --write-baseline agents/advisor-metadata/src/dd_agent_advisor_metadata/evals/baseline.json /tmp/metadata
```

Commit the rewritten baseline on its own, saying which cases changed and why.

## Limits

- **Categories need a model.** The evaluation's conductor serves `mcp-subjects` in process
  behind the tool gateway and grants it to the librarian, as a deployment does, so a run with
  `DD_METADATA_SUGGESTER=model` has the model choose each category from the fields it retrieves
  there and scores it. The committed baseline is the template suggester's, which calls no model
  and so recalls no category, and `terms_cited` applies to no case in it.
  `tests/test_metadata_evals.py` runs the whole evaluation with a fake model, through the same
  gateway: one that answers with a curator's category is recalled and cited for every case, and
  one that answers with a code the classification does not hold is offered nowhere. Keywords from
  terminology services are the spike #956.
- **One category per record.** ORDA's requirements ask for one category entry, so a case whose
  curator names two can recall at most half of them.
- **The labels are provisional and hand-written.** The cases are written to look like ORDA
  deposits, but none is a real record, and no curator has reviewed the categories chosen. A
  labelled corpus of ORDA records is to replace them (TODO(#22)).
- **The template path.** The baseline measures the rules: the template suggester calls no model
  and suggests nothing.
- **One standard.** Every case drafts DataCite. Drafting in other standards is evaluated under
  TODO(#1364).
