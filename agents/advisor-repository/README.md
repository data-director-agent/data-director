# advisor.repository

**Model-backed alpha** (`0.1.0-alpha.3`): the Repository Librarian persona
([Agents](../../docs/specs/agents.md)). Exploratory, and likely to change shape. A model only
writes each repository's rationale; it never chooses or judges a repository.

The repository advisor helps with Phase 3 of the Blueprint's process flow, repository selection
(§8.2, Figure 3). It serves four of the phase's steps:

| Step | What the agent does |
|---|---|
| `repository.recommend` (R1) | Shortlists repositories from the whole of re3data, with the researcher's own institution's repository from DataCite where re3data does not list it, or describes the ones mandated, and describes any the researcher asks about. |
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
`embargoed` or `restricted`), any mandated repositories, any repositories the researcher asked
about, and the researcher's affiliation. With mandated repositories the agent describes them.
With none, it shortlists (the two branches of Figure 3), and its statement says that a funder,
journal or institution may still require a repository, since an empty list often means only
that no policy source records one.

`mandated` is only for a requirement: one a policy result found, or one the researcher says a
funder, journal or institution imposes. A repository the researcher merely names or asks about
("what about Zenodo?") goes in `asked_about` (#1167). It is described with the same `meets` and
`misses`, with the basis `asked_about`, and listed before the shortlist rather than instead of
it. If the shortlist also ranks it, it keeps its score and `ranked_by`. The app shows it as
"You asked about this", never as "Mandated".

In a project, a repository that a sharing commitment of the data management plan names, once the
researcher has confirmed the commitment, is described the same way with the basis `in_plan`: a
plan's choice is not a mandate (#1233). A plan that names several repositories for one output, as when it deposits the output in the
institution's repository and offers a copy to a partner archive, gives a commitment for each, and
each is described (#1334). The app shows it as "In your plan". A name re3data does
not list, such as "ReShare" for the UK Data Service's self-deposit repository, is read through the
short, sourced list in `aliases.yaml`, and the statement says so.

`RepositoryOptions` holds one candidate per repository. A candidate names its records only in
`grounded_on`: first its registry record, re3data's, cited by the record's own DOI, or, for a
repository re3data does not list, DataCite's, cited by its address in DataCite's API; then the
FAIRsharing database record that re3data cross-references, when there is one; and what the
deployment's profile vouches for, when it names the repository (*The deployment's own
repositories* below). What the reader is shown about the repository is the
evidence `content` of those records ([Evidence and grounding](../../docs/specs/grounding.md)). The candidate adds:

- three answers read from the records, each `yes`, `no` or `unstated`: `assigns_pids`,
  `commercial` and `fee_required`;
- `meets` and `misses`: the needs the repository meets, and those it does not meet or its records
  leave open;
- `notes`: facts to weigh, such as a fee for users, a commercial platform supplier, the
  certificates listed, and the deposit conditions FAIRsharing records;
- `ranked_by`: for a recommended repository, why it is on the shortlist and in its place, one
  sentence per ranking signal, such as `Matches the theme "hydrology" (1 of 2 given).` Empty
  for a mandated one, and for one asked about that the shortlist did not rank.

Mandated names, and names in the plan or asked about, with no single record in re3data or, after
it, DataCite are listed in `not_found`. A name re3data does not list but DataCite does, such as
many an institution's own repository, is described like any other, and can be chosen (#1342).
Those neither lists under any name, such as a local archive that mints no DataCite DOIs, are
also in `unlisted`, each with its basis, so that the researcher still sees them
as "In your plan" or "You asked about this" (#1334). Nothing is said about their terms, fees or
identifiers, since there is no record to read them from, and the statement says to check with the
repository. A succeeded payload must rest on a record retrieved, so a run with nothing but such
names to show abstains, and names them in its statement.

## How it decides

The pipeline is retrieve, assess, rank, explain. Retrieval comes first, and no model chooses a
repository or makes a judgement:

- **Search.** One query per theme and per kind of data over every repository in the registry
  (BM25), where a hit must contain every word of the query, as re3data's own search requires.
  Each theme is also matched to the DFG subjects it names (`dfg.py`), and the repositories re3data
  files under them are retrieved too, so a repository whose record never uses the theme's word is
  still found. A further query names the researcher's institution, and the generalist
  repositories listed in `ranking.yaml` (Zenodo, Harvard Dataverse, OSF, Dryad, figshare and
  Mendeley Data) are taken by identifier.
- **Assessment** (`assess.py`). Fixed rules over registry fields. Where the records are silent
  the answer is `unstated`, never a guess. A commercial institution counts as an operator only
  when its responsibility is general or funding. A commercial technical supplier, such as
  Figshare for ORDA, is a note.
- **Ranking** (`ranking.yaml`). The discipline is judged from the themes alone. Each theme is
  graded from 0 to 1, half on the text (a hit's BM25 score relative to the best hit for that
  theme) and half on the DFG subject: full marks for a repository filed under the subject the
  theme names, less for one filed only under the subject just above it or two levels above, and
  nothing for the top level (Natural Sciences, say). A theme that names no DFG subject, such as
  "moorland", is graded on its text alone, as is a record that lists no subjects. A theme names
  a subject when every word of the theme is in one field of the subject's name, and the closest
  such subjects are kept: "hydrology" names `34601 Hydrogeology, Hydrology, ...`, and "fluid
  dynamics" names none. A repository scores by the mean of its theme grades. The kinds of data
  add a little, never enough to
  recommend a repository on their own, since a kind of data such as "images" is found in
  repositories of every discipline. A generalist scores below a repository that matches every
  theme (Figure 3's "domain-specific or generalist"); when no repository of the discipline is
  found, the statement says that only generalist and institutional repositories are offered and
  suggests the broad field of study, since a narrow topic such as "moorland" may match none.
  Ranking also uses whether the repository offers the access the data needs, and whether an
  institution in the researcher's country operates it: a small weight that puts such a
  repository above an equal or slightly closer match elsewhere, and never adds one on its own
  (#741). The country is `country` when given, else the one re3data records for the
  affiliation's institution, so no country, funder or repository is written into the rules.
  Search folds English plurals to singulars (`-ies` to `-y`, a final `s` dropped unless the
  word ends in `ss`, `us` or `is`) in queries and records alike, so the theme "environmental science" finds a
  record that says only "sciences".
- **The researcher's institution's repositories that re3data does not list** are retrieved from
  DataCite (*Sources* below): those whose DataCite member is the researcher's institution, by ROR
  where both have one, else by exact name, and those the deployment's profile names as its
  institution's. They are ranked as re3data's are: a DataCite record gives its member as the
  operator, `DOI` as its PID system, its repository types, and how many datasets it has
  registered; it states no access, licences or fees, so those are `unstated` unless the profile
  vouches for them. One typed only `institutional` takes deposits from its members, so it is
  offered only to them.
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
- **Reserved places** (`reserve`). Within the cap, a place is kept for at least one generalist
  whenever one qualifies, so a broad theme that finds five repositories of the discipline cannot
  crowd every generalist out, and a researcher who does not know where to deposit always has a
  usable option (#1169). A generalist listed only because of its place says so in `ranked_by`.
- **Order at an equal score** (`tie_break`). A commercial operator is listed after the others,
  and then a repository that lists a deposit fee, and then one that assigns no persistent
  identifiers; none is dropped. re3data does not tell some generalists apart (Zenodo, Harvard
  Dataverse and OSF answer all three alike), so the order of `generalists` is a stated
  preference that settles them, never the alphabet. Repositories of the same kind of fit and
  score each say in `ranked_by` that they are ranked equal, and by which rule. Certification
  carries no weight, because Figure 3 says paid certification must not outweigh free
  evaluation.
- **Credit.** Every statement ends by crediting re3data, naming the export it read, and DataCite,
  naming the day its snapshot was fetched.
- **Explanation.** By default a model writes the rationale; `DD_REPOSITORY_EXPLAINER=template`
  writes it from a template and needs no key. The model writes the rationale only, from
  `system_prompt.md`, in one call over the candidates already chosen. It is sent the needs
  (themes, kinds of data, access, the affiliation's name) and, for each repository, its registry
  text, its `meets`, `misses` and `notes`, and its description, never research data. If its
  rationale for a repository names a re3data or FAIRsharing identifier it was not given, the
  template rationale is used instead and the text says so. `rationale_derivation` records which
  wrote each one. A repository the researcher chose for the project (basis `chosen`) is described
  when nothing else is asked.

## Configuration

- `DD_REPOSITORY_RETRIEVAL`: how FAIRsharing's database records are read: `snapshot` (the
  default) or `live`. The live route is public and needs no account; when it fails the agent falls
  back to the snapshot, marked stale. re3data is always read from the pinned registry.
- `DD_REPOSITORY_EXPLAINER`: `model` (the default; `anthropic` is its older name) or `template`,
  which calls no model and needs no key. The provider, model and key are set as for every advisor
  ([AI models](../../docs/guide/operations/ai-models.md)). With the model on, the agent's card
  declares the model it sends data to. An unknown value, or a model that cannot be configured,
  stops `serve` at start-up; with the variable unset and no key, the error says to set
  `DD_REPOSITORY_EXPLAINER=template`.

What the deployment allows is not set here: it comes from the institutional profile
([Policy and identity](../../docs/specs/policy-and-identity.md)).

## Run it

```sh
uv run dd-sources prepare                          # build the pinned re3data registry, once
DD_REPOSITORY_EXPLAINER=template uv run dd-advisor-repository serve --port 8109   # no model key
uv run pytest agents/advisor-repository
```

Without `DD_REPOSITORY_EXPLAINER=template` the agent needs a model key. The workbench's samples
are `workbench/samples/repository-needs.json`, `repository-mandated.json`,
`repository-asked-about.json` and `repository-in-plan.json`. The evaluation is in
[`src/dd_agent_advisor_repository/evals/README.md`](src/dd_agent_advisor_repository/evals/README.md).

## Sources

**re3data.** The agent reads every repository in re3data from one monthly export, pinned in
`data/re3data/manifest.json` by URL and SHA-256. The registry is a built source, declared to
`dd-sources` by `registry.SOURCE` under the `dd.sources` entry point (`pyproject.toml`), so the
command that builds every agent's sources builds it:

```sh
uv run dd-sources prepare         # build registry.jsonl (and any other built source) as pinned
uv run dd-sources check           # does each built source match its pin?
uv run dd-re3data fetch           # build registry.jsonl alone; also runs the `re3data` tests
uv run dd-re3data fetch --update-pin [--month YYYY-MM]   # pin another month's export
uv run scripts/pin_re3data.py     # then pin both sources.yaml files to it
```

`dd.py setup` and `start`, Docker Compose, CI and `deploy/deploy.sh` run `dd-sources prepare`.
It downloads an archive once per pin and keeps it in `data/re3data/archives/` (or in `re3data/`
under a `--cache-dir`), so a run never asks re3data. A registry that is
missing or does not match its pin is an error that names the command to run, and the agent
abstains. A registry that does not match its pin also stops the app from starting. A missing one
does not: the harness warns with the command, and re3data evidence is unresolved rather than
verified. Neither the archive nor the registry is committed. A
pull request moves the pin each month: `.github/workflows/re3data.yml` pins the newest export on
the 3rd, runs this agent's tests and opens it for review, with the repositories added and removed.

Evidence from it carries the `snapshot_ref` `re3data:export:YYYY-MM`, and both `sources.yaml` files
pin `registry.jsonl` under that label, so the harness's source check verifies every re3data
record the agent cites ([Evidence and grounding](../../docs/specs/grounding.md)). A change to
`records.py` changes the registry's bytes: pin it again with
`fetch --update-pin --month <the pinned month>` and `scripts/pin_re3data.py` in the same pull
request; CI fails while either `sources.yaml` disagrees with the manifest
(`scripts/pin_re3data.py --check`). How we credit re3data and keep our load on it low is in
[`data/re3data/SOURCE.md`](data/re3data/SOURCE.md).

**DataCite.** `data/datacite/repositories.jsonl` holds the repositories DataCite registers that
re3data does not list: active ones, of client type repository, that link to no re3data record and
have registered at least one Dataset DOI, which tells a data repository from a press or a theses
service. DataCite's metadata are CC0. The snapshot is committed and pinned in
`data/datacite/manifest.json`, as the FAIRsharing snapshot is, since DataCite publishes no
archive that could be fetched again to the same bytes; `uv run dd-datacite fetch` fetches it anew,
and `uv run dd-datacite check` checks it against its pin. Both `sources.yaml` files pin it under
`datacite:repositories:YYYY-MM-DD`, so the source check verifies every DataCite record the agent
cites. A DataCite record whose address is a re3data record's is that repository, which re3data
describes with more facts, and is left out even where DataCite does not link the two. The dataset
count is kept as a string of digits: A2A carries an integer in evidence as a float, whose hash
would then fail (TODO(#333)). How we credit DataCite is in
[`data/datacite/SOURCE.md`](data/datacite/SOURCE.md).

**The deployment's own repositories.** A deployment names its institution's repositories in its
profile (`institution_repositories`,
[Configuration](../../docs/guide/operations/configuration.md)), each by its re3data or DataCite
identifier, with what it vouches for that no registry holds: which institution's it is, its
access, licences and whether it charges a fee. The conductor gives them to the agent in
`RepositoryNeeds.institution_repositories` (`GivenInstitutionRepositories`), and whatever a caller
sent there is replaced. Such a repository is the institution's for a researcher of that
institution, whoever registered it, and what the profile vouches for stands over the registry's
silence (`institution.py`): the deployment knows its own repository better than a registry, as a
steward's requirement override does ([Deposit](../../docs/specs/deposit.md), invariant 5). It is
cited as a second evidence item, `institution:<identifier>`, under the profile's reference, which
the harness's source check resolves against the profile it loaded.

**FAIRsharing.** `data/fairsharing/` holds a committed snapshot of the database records that
re3data cross-references for the repositories the agent was first tested on. It is pinned in
both `sources.yaml` files. Rebuild it with
`uv run python agents/advisor-repository/scripts/build_fairsharing_snapshot.py`, then pin the new
file. Most repositories in the registry have no record in it. Their candidates stand on re3data
alone unless `DD_REPOSITORY_RETRIEVAL=live`: TODO(#487).

A cross-reference is followed as re3data states it. It need not be returned: re3data's CEDA
Archive names FAIRsharing's record of the CEDA centre, which names a different re3data entry.

The tests build a registry from `tests/data/re3data-export-fixture.zip`, about 30 records cut
from the export (`tests/data/SOURCE.md`), so they need no network.

## Limits

- re3data shows that a fee is required, but not how much, and does not say who pays. It has no
  value for "no fee", so a fee it does not list is reported as `unstated`, never `no`, and the
  app shows "not stated by the repository, check with them". PID costs are not covered.
  TODO(#322)
- re3data names each certificate, with its dates, but only the names are kept, so a lapsed
  certificate is reported as if current. TODO(#485). Free quality evaluations are not consulted.
  TODO(#323)
- re3data lists the PID systems a repository uses, but not whether assignment is automatic.
- Only institutions that re3data or DataCite lists, or the profile names, are matched to the
  researcher's affiliation, which the caller gives: it is not read from the researcher's identity
  or ORCID record. A repository that mints no DataCite DOIs and that re3data does not list cannot
  be offered or chosen; OpenDOAR would cover many such, once its licence is confirmed to allow a
  pinned copy. DataCite writes its members' countries in two letters, re3data in three, so a
  DataCite repository adds nothing to the country rule. There is no preference for a deployment's
  approved repositories beyond its own institution's (TODO(#320)), and none for the researcher's
  country, so a search for "social science" offers national archives from anywhere (TODO(#486)).
- re3data's subjects follow the DFG classification, and its content types the COAR resource
  types (`dataset`, `image`), so a kind of data matches only the words re3data uses.
- The metadata standards each repository lists are in the evidence, but the chosen repository
  does not yet shape Phase 4. TODO(#321)
