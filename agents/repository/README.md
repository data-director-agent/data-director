# repository.advisor

**Alpha** (`0.1.0-alpha`): exploratory, and likely to change shape.

The repository advisor helps with Phase 3 of the Blueprint's process flow, repository selection
(§8.2, Figure 3). It serves four of the phase's steps:

| Step | What the agent does |
|---|---|
| `repository.recommend` (R1) | Shortlists repositories from re3data, or describes the ones mandated. |
| `repository.pid` (R7) | Reports whether re3data lists a persistent identifier system the repository uses. |
| `repository.access-and-costs` | Compares the access the data needs with what the repository offers, and reports listed fees. |
| `repository.certification` | Reports the certificates re3data lists. They carry no weight in ranking. |

The fifth step, `repository.mandated`, is a policy question. It is answered from funder, journal
and institutional policy records by `policy.advisor` (#324), and passed to this agent as
`RepositoryNeeds.mandated`. The two agents split R1's "flag conflicts" between them:
`policy.advisor` flags policies that disagree, and this agent flags a mandated repository that
does not meet a need, such as one that offers no embargo. Neither resolves a conflict. The
researcher chooses the repository (#199); the agent never does.

## Input and output

`RepositoryNeeds` has the themes and kinds of data, the access decided in Phase 2 (`open`,
`embargoed` or `restricted`), any mandated repositories, and the researcher's affiliation. With
mandated repositories the agent describes them. With none, it shortlists (the two branches of
Figure 3).

`RepositoryOptions` holds one candidate per repository. A candidate names its records only in
`grounded_on`: its re3data record, and the FAIRsharing database record that re3data
cross-references, when there is one. What the reader is shown about the repository is the
evidence `content` of those records (ADR-0015). The candidate adds:

- three answers read from the records, each `yes`, `no` or `unstated`: `assigns_pids`,
  `commercial` and `fee_required`;
- `meets` and `misses`: the needs the repository meets, and those it does not meet or its records
  leave open;
- `notes`: facts to weigh, such as a fee for users, a commercial platform supplier, the
  certificates listed, and the deposit conditions FAIRsharing records.

Mandated names with no re3data record are listed in `not_found`.

## How it decides

The pipeline is retrieve, assess, rank, explain. Retrieval comes first, and no model chooses a
repository or makes a judgement:

- **Search.** One re3data query per theme and kind of data, because re3data's search requires
  every word of a query to match. A further query names the researcher's institution.
- **Assessment** (`assess.py`). Fixed rules over registry fields. Where the records are silent
  the answer is `unstated`, never a guess. A commercial institution counts as an operator only
  when its responsibility is general or funding. A commercial technical supplier, such as
  Figshare for ORDA, is a note.
- **Ranking** (`ranking.yaml`). Ranking uses the subject fit, whether the researcher's
  institution operates the repository, and whether it offers the access the data needs. A
  repository closed to deposits is never recommended. A commercial operator is listed after
  others with an equal score, but never dropped. Certification carries no weight, because
  Figure 3 says paid certification must not outweigh free evaluation. The researcher's own
  institutional repository is offered beyond the cap.
- **Explanation.** The template is the default. With `DD_REPOSITORY_EXPLAINER=anthropic`, a model
  writes the rationale only, from `system_prompt.md`, and is sent registry text and the needs,
  never research data.

## Configuration

- `DD_REPOSITORY_RETRIEVAL`: `snapshot` (the default) or `live`. Both live routes are public and
  need no account. With `live`, the agent falls back to the snapshots, marked stale, when a route
  fails.
- `DD_REPOSITORY_EXPLAINER`: `template` (the default) or `anthropic`, with `DD_MODEL_ID` and the
  key as for the standards advisor (ADR-0026).

## Sources

`data/re3data/` and `data/fairsharing/` hold the committed snapshots, one record per line in the
form that is hashed. They are pinned in `workbench/sources.yaml` and `app/config/sources.yaml`, so
the harness's source check verifies the evidence against them (ADR-0016). To rebuild them, run
`uv run python agents/repository/scripts/build_snapshot.py`, then pin the new files. The
re3data identifiers kept are listed in `data/re3data/ids.txt`.

A cross-reference is followed as re3data states it. It need not be returned: re3data's CEDA
Archive names FAIRsharing's record of the CEDA centre, which names a different re3data entry.

## Limits

- re3data shows that a fee is required, but not how much, and does not say who pays. PID costs
  are not covered. TODO(#322)
- re3data's API names most certificates only as "other"; a repository's CoreTrustSeal status is
  often only in its free-text remarks. Free quality evaluations are not consulted. TODO(#323)
- re3data lists the PID systems a repository uses, but not whether assignment is automatic.
- Only institutions that re3data lists are matched to the researcher's affiliation. There is no
  preference for the deployment's approved repositories, and none for the researcher's country,
  so a live search for "social science" offers national archives from anywhere. TODO(#320)
- The metadata standards each repository lists are in the evidence, but the chosen repository
  does not yet shape Phase 4. TODO(#321)
- The FAIRsharing client is a copy of the standards advisor's, since an agent may not import
  another (ADR-0031). TODO(#280)
