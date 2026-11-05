# advisor.repository

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
and institutional policy records by `advisor.policy` (`agents/advisor-policy/`), and passed to this agent
as `RepositoryNeeds.mandated`. The two agents split R1's "flag conflicts" between them:
`advisor.policy` flags policies that disagree, and this agent flags a mandated repository that
does not meet a need, such as one that offers no embargo. Neither resolves a conflict. The
researcher chooses the repository (#199); the agent never does.

## Input and output

`RepositoryNeeds` has the themes and kinds of data, the access decided in Phase 2 (`open`,
`embargoed` or `restricted`), any mandated repositories, and the researcher's affiliation. With
mandated repositories the agent describes them. With none, it shortlists (the two branches of
Figure 3), and its statement says that a funder, journal or institution may still require a
repository, since an empty list often means only that no policy source records one.

`RepositoryOptions` holds one candidate per repository. A candidate names its records only in
`grounded_on`: its re3data record, and the FAIRsharing database record that re3data
cross-references, when there is one. What the reader is shown about the repository is the
evidence `content` of those records ([Evidence and grounding](../../docs/specs/grounding.md)). The candidate adds:

- three answers read from the records, each `yes`, `no` or `unstated`: `assigns_pids`,
  `commercial` and `fee_required`;
- `meets` and `misses`: the needs the repository meets, and those it does not meet or its records
  leave open;
- `notes`: facts to weigh, such as a fee for users, a commercial platform supplier, the
  certificates listed, and the deposit conditions FAIRsharing records;
- `ranked_by`: for a recommended repository, why it is on the shortlist and in its place, one
  sentence per ranking signal, such as `Matches the theme "hydrology" (1 of 2 given).` Empty
  for a mandated one.

Mandated names with no re3data record are listed in `not_found`.

## How it decides

The pipeline is retrieve, assess, rank, explain. Retrieval comes first, and no model chooses a
repository or makes a judgement:

- **Search.** One re3data query per theme and per kind of data, because re3data's search
  requires every word of a query to match; the snapshot search requires it too. A further query
  names the researcher's institution, and the generalist repositories listed in `ranking.yaml`
  (Zenodo, figshare, Harvard Dataverse, Dryad, OSF and Mendeley Data) are fetched by identifier.
- **Assessment** (`assess.py`). Fixed rules over registry fields. Where the records are silent
  the answer is `unstated`, never a guess. A commercial institution counts as an operator only
  when its responsibility is general or funding. A commercial technical supplier, such as
  Figshare for ORDA, is a note.
- **Ranking** (`ranking.yaml`). The discipline is judged from the themes alone: a repository
  scores by the share of the themes it matches. The kinds of data add a little, never enough to
  recommend a repository on their own, since a kind of data such as "images" is found in
  repositories of every discipline. A generalist scores below a repository that matches every
  theme (Figure 3's "domain-specific or generalist"); when no repository of the discipline is
  found, the statement says that only generalist and institutional repositories are offered and
  suggests the broad field of study, since a narrow topic such as "moorland" may match none.
  Ranking also uses whether the repository offers the access the data needs.
- **The researcher's institution** is a fallback, in case no more specific destination (a
  repository of the discipline, or one a funder, journal or project requires) suits the data
  (#441). Affiliation adds no score. The shortlist is ordered by kind of fit (`order`): the
  dataset's discipline, then the institution's own repositories, then generalists. An
  institution's repository that matches the discipline is ranked as any other; one that does not
  is offered as the fallback, and its `ranked_by` says so.
- **Left out.** A repository closed to deposits is never recommended, nor is one that takes
  deposits only from its own institution's members (re3data's "institutional membership"
  restriction, or a repository typed only `institutional`) unless the researcher's institution
  operates it. The researcher's own institutional repository is offered beyond the cap, unless
  it lacks the access the data needs, and takes no other repository's place, so naming an
  institution adds to the shortlist and removes nothing.
- **Order at an equal score.** A commercial operator is listed after the others, and then a
  repository that lists a deposit fee; neither is dropped. Certification carries no weight,
  because Figure 3 says paid certification must not outweigh free evaluation.
- **Explanation.** The template is the default. With `DD_REPOSITORY_EXPLAINER=anthropic`, a model
  writes the rationale only, from `system_prompt.md`, and is sent registry text and the needs,
  never research data.

## Configuration

- `DD_REPOSITORY_RETRIEVAL`: `snapshot` (the default) or `live`. Both live routes are public and
  need no account. With `live`, the agent falls back to the snapshots, marked stale, when a route
  fails.
- `DD_REPOSITORY_EXPLAINER`: `template` (the default) or `anthropic`, with `DD_MODEL_ID` and the
  key as for the standards advisor ([Policy and identity](../../docs/specs/policy-and-identity.md)).

## Sources

`data/re3data/` and `data/fairsharing/` hold the committed snapshots, one record per line in the
form that is hashed. They are pinned in `workbench/sources.yaml` and `app/config/sources.yaml`, so
the harness's source check verifies the evidence against them ([Evidence and grounding](../../docs/specs/grounding.md)). To rebuild them, run
`uv run python agents/advisor-repository/scripts/build_repository_snapshot.py`, then pin the new files. The
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
  another ([System and boundaries](../../docs/specs/system.md)). TODO(#280)
