# advisor.policy

**Alpha** (`0.1.0-alpha`): exploratory, and likely to change shape.

The policy advisor checks what the data policies of a project's funders, journals and institution
ask of its data. It serves two steps of the Blueprint's process flow (§8.2):

| Step | What the agent does |
|---|---|
| `governance.policies` (Phase 2, Figure 2) | Matches each funder, journal and institution to its FAIRsharing policy records, and reports what each asks and where they differ. |
| `repository.mandated` (Phase 3, Figure 3) | Reports the repositories a matched policy requires, in the form `advisor.repository` takes as `RepositoryNeeds.mandated`. |

The guidance note to Figure 2 suggests FAIRsharing's policy records as the source. They are
curated summaries, not the policies themselves, and say nothing of most of what a researcher
needs: which repository, by when, for how long the data may be withheld, under which licence. So
the agent also reads each policy's own text, and a model reports what it states, quoting the
passage each obligation comes from; the agent keeps only quotes it finds in the text. Every
result still needs a person to confirm it against the policy. The agent flags where policies
differ and never decides which applies.

## Input and output

`PolicyContext` names the actors, each a `funder`, `journal` or `institution` with a name and,
when known, the FAIRsharing identifier of its policy. A funder may also carry its ROR identifier
(`ror_id`), which is how the researcher answers when its name is ambiguous. A journal may carry
its ISSN (`issn`), which identifies it and its publisher exactly. Any actor may carry the address
of its policy's page or PDF (`policy_url`), which is read as well as the address any matched
record names. It may also give the
disciplines, the kinds of data and the publication date.

`PolicyChecks` holds:

- `policies`: one entry per policy record matched to an actor. The record is named only in
  `grounded_on`; its name, clauses and relations are the evidence `content` ([Evidence and grounding](../../docs/specs/grounding.md)). Each
  entry has one obligation per kind (`deposit`, `data_availability_statement`, `repository`,
  `standard`, `embargo`, `licence`, `timing`), each `required`, `recommended` or `unstated`,
  with the value the curators recorded in `recorded_as`. It also has notes and a rationale.
- `conflicts`: each kind of obligation that matched policies state with different strengths,
  grounded on every policy involved.
- `mandated_repositories`: the repositories a matched policy requires.
- `no_record`: the actors with no policy record.
- `funders`: each funder identified in ROR, grounded on its ROR record (the identifier is stated
  there only), with the Crossref Funder ID ROR prefers, so that both can be passed on.
- `readings`: one per policy text fetched, grounded on that text (cited by its address, with the
  whole text read as the evidence `content`) and on the record it was reached from, if any. Each
  has a `status` (`read`, `not_read` or `unreadable`), the obligations it `stated`, each with its
  kind, strength, value and the `quote` it comes from, what was `dropped` and why, and a `reason`
  where it was not read or was read in part.
- `journals`: each journal identified in Crossref, with its ISSN, grounded on its Crossref
  records, which name its publisher.
- `ambiguous`: each funder whose name could mean more than one organisation in ROR, and each
  journal title Crossref gives to journals of different publishers, grounded on every candidate,
  likeliest first. Its policy was not looked up, and the statement asks the researcher which they
  mean, by ROR identifier or ISSN.

## How it decides

Retrieval comes first, and no model matches a policy or states an obligation:

- **Identifying funders** (`resolve.py`, `ror.py`). Each funder is looked up in ROR, by its ROR
  identifier when given, otherwise by an exact match, ignoring case and spacing, against every
  name, acronym and alias ROR records for an active organisation. One match is resolved, and
  FAIRsharing is searched by each of its English names as well as the name given. More than one
  is not guessed: the candidates are returned and the researcher is asked, funders and
  organisations with a Crossref Funder ID shown first. A name such as "UKRI-NERC" that ROR does
  not hold is read through ROR's own parent relationships. No alias table is kept. When ROR
  cannot be read, funders are searched by the name given and the statement says so.
- **Identifying journals** (`journals.py`, `resolve.py`). Most journals follow their publisher's
  data policy and have no FAIRsharing record of their own. Each journal is looked up in
  Crossref's public journal API, by its ISSN when given, otherwise by an exact match of its title,
  ignoring case and spacing. Records that all name one publisher identify it, and FAIRsharing is
  searched by the journal's title and by the publisher's name, as Crossref gives it, without
  its legal form ("Elsevier BV" as "Elsevier") and without a bracketed imprint ("Wiley (Blackwell
  Publishing)" as "Wiley"). A record found by the publisher's name is kept only
  if FAIRsharing types it as a journal publisher's policy, so another of the publisher's journals'
  policies is not matched. Records naming different publishers are not guessed: the researcher is
  asked for the ISSN. When Crossref cannot be read, the journal is searched by the name given and
  the statement says so. No table of journals or publishers is kept.
- **Matching** (`match.py`). An actor given with a FAIRsharing identifier is fetched by it.
  Otherwise each of its names is searched, and a record is kept only when FAIRsharing types it for the
  actor's role (a journal matches a journal or journal publisher policy) and its name or
  abbreviation contains one of those names as whole words. At most three records are kept per
  actor, shortest name first, so a publisher's own policy comes before its journals'.
- **Obligations** (`assess.py`). Read from curated fields by fixed rules: `deposit` from
  `sharing_data.mandated_data_sharing`, `data_availability_statement` and `licence` from their
  `required` values, and `repository` and `standard` from the record's `requires` and
  `recommends` relations. `required` and `yes` give `required`; `suggested` and `recommended`
  give `recommended`; anything else gives `unstated`. A value such as `no` is kept in
  `recorded_as`, since a record that says a policy does not require something is not the same as
  one that says nothing.
- **Notes**. The agent notes a policy whose subjects do not include the discipline, a policy
  dated after the publication, a policy that allows exceptions to sharing, and a required data
  management plan.
- **Conflicts**. When matched policies state the same kind of obligation with different
  strengths, such as a funder requiring deposit where the institution only recommends it, the
  difference is listed for a person to resolve.
- **Reading the policy's own text** (`policy_text.py`, `pdf_text.py`, `extract.py`). Each matched
  record's `homepage`, and each `policy_url` given, is fetched once: an HTML page is turned into
  text without its scripts, styles, navigation, header and footer; a PDF is read with `pypdf`;
  anything else is unreadable. A short landing page that links to PDFs on its own site, as many
  funders' publication pages do, has up to two of them read with it, each named in the evidence. Every page is fetched before any model is called. A model is then
  given the text, as quoted data in the user turn, and returns, for each kind of obligation the
  text states, its strength, what it asks and the passage that says so, against a schema. The
  code keeps an obligation only if its quote is in the text, word for word once typography and
  white space are made plain, and at least twenty characters long; it drops the rest and says
  why. This adds to the record's obligations and never changes them: where the two differ, both
  are shown and the statement says so. Without a model, nothing is fetched.
- **Explanation.** The template is the default. With `DD_POLICY_EXPLAINER=model`, a model
  writes the rationale only, from `system_prompt.md`. It is sent registry text and the context,
  never research data.

## Configuration

The deployment's institutional profile sets the agent's options (`agent_settings`,
[Policy and identity](../../docs/specs/policy-and-identity.md)):

- `journals`: `crossref` (the default) identifies journals in Crossref's public API, which needs
  no account; `off` matches journals by the name given only.
- `policy_text`: `read` (the default) fetches each policy's own page and has the agent's model
  read it; `off` reads FAIRsharing's records only. Reading needs a model: the one the agent's
  settings configure (`DD_MODEL_PROVIDER`, `DD_MODEL_ID` and the provider's key, as for the
  explainer), whether or not the explainer uses it. With none, the text is not read and the
  statement says so.

Its environment variables:

- `DD_POLICY_RETRIEVAL`: `snapshot` (the default) or `live`. Live search needs a FAIRsharing
  account: `FAIRSHARING_LOGIN`, and `FAIRSHARING_PASSWORD` or `FAIRSHARING_PASSWORD_FILE`.
  `uv run scripts/dd.py setup` writes them when it is given a login. With `live`, the agent
  falls back to the snapshot, marked stale, when the route fails.
- `DD_POLICY_ROR`: `snapshot` (the default) reads the ROR registry built from its pinned dump;
  `live` asks `api.ror.org`, which needs no account, and falls back to that registry, marked
  stale, when the route fails.
- `DD_POLICY_EXPLAINER`: `template` (the default) or `model`, with the provider, model and
  key as for the standards advisor ([AI models](../../docs/guide/operations/ai-models.md)) ([Policy and identity](../../docs/specs/policy-and-identity.md)).

## Sources

`data/fairsharing/` holds the committed snapshot, one record per line in the form that is hashed.
Its label, `fairsharing-policy:snapshot:<date>`, differs from the repository advisor's copy of
FAIRsharing's database records. It is pinned in `workbench/sources.yaml` and
`app/config/sources.yaml`, so the harness's source check verifies the evidence against it
([Agents](../../docs/specs/agents.md)). The identifiers kept are listed in `data/fairsharing/ids.txt`. To rebuild, run
`uv run python agents/advisor-policy/scripts/build_policy_snapshot.py` with the FAIRsharing login set, then pin
the new file.

`data/ror/` pins one ROR data dump (CC0; see `data/ror/SOURCE.md`). The registry built from it
is not committed: `uv run dd-sources prepare` builds it, as it builds the re3data registry, and
its label is `ror:dump:<version>`. `uv run dd-ror fetch --update-pin` pins the newest dump.

## Limits

- FAIRsharing's policy records are coarse, and many institutions have none. They have no field
  for embargoes or for when data must be shared, so those obligations are always `unstated` in
  the record's obligations; the policy's own text may state them, in `readings`. TODO(#302)
- The FAIRsharing API returns no relations from a policy to the databases and standards it
  names, even for policies that list repositories on the website. So the repository and standard
  obligations are `unstated`, and `mandated_repositories` is empty, until a route provides them.
  An empty list is not evidence that no repository is mandated, and the statement says so,
  naming the actors with no record as unchecked. A repository the policy's text requires is in
  `readings` and the statement, read by a model; it is not yet passed to `advisor.repository`
  as mandated. TODO(#302, #331, #753)
- A policy's text is read only where a matched record names its page or the researcher gives
  one: an actor with no record and no `policy_url` is not read. The page is read as it is when
  fetched, which may not be the version that applied at the publication date, and only its first
  60,000 characters (or 60 pages of a PDF) are read. A page that loads its text with scripts is
  read as empty. Pages are read live and not pinned, so the source check reports them as
  unresolved. Whether a model's reading of a quote is right is for the person confirming it and
  for evaluation; the code checks only that the quote is in the text.
- An actor is matched by name, and only to a record whose name contains one of its names. A
  funder is searched by every name ROR gives it, and a journal by its Crossref title and its
  publisher's name, but an institution only by the name given. A publisher whose FAIRsharing name
  differs from Crossref's by more than its legal form ("Springer Science and Business Media" and
  "Springer Nature") is not found.
- Crossref is read live; there is no pinned copy, so the source check reports its evidence as
  unresolved, as it does every live route. Its search reads the first page of results only, so a
  common title may need its ISSN. ROR's live search likewise reads the first page of results
  only, so a common name may need the dump or the identifier.
- A funder's affiliation country does not yet rank its ROR candidates.
- Differences are found between strengths only. Two policies that require different
  repositories are not yet compared. TODO(#331)
- The FAIRsharing client is a copy of the standards advisor's, since an agent may not import
  another ([System and boundaries](../../docs/specs/system.md)). TODO(#280)
