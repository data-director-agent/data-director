# advisor.policy

**Alpha** (`0.1.0-alpha`): exploratory, and likely to change shape.

The policy advisor checks what the data policies of a project's funders, journals and institution
ask of its data. It serves two steps of the Blueprint's process flow (§8.2):

| Step | What the agent does |
|---|---|
| `governance.policies` (Phase 2, Figure 2) | Matches each funder, journal and institution to its FAIRsharing policy records, and reports what each asks and where they differ. |
| `repository.mandated` (Phase 3, Figure 3) | Reports the repositories a matched policy requires, in the form `advisor.repository` takes as `RepositoryNeeds.mandated`. |

The guidance note to Figure 2 suggests FAIRsharing's policy records as the source. They are
curated summaries, not the policies themselves, so every result needs a person to check it
against the policy text. The agent flags where policies differ and never decides which applies.

## Input and output

`PolicyContext` names the actors, each a `funder`, `journal` or `institution` with a name and,
when known, the FAIRsharing identifier of its policy. A funder may also carry its ROR identifier
(`ror_id`), which is how the researcher answers when its name is ambiguous. It may also give the disciplines, the kinds
of data and the publication date.

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
- `ambiguous`: each funder whose name could mean more than one organisation in ROR, grounded on
  every candidate, likeliest first. Its policy was not looked up, and the statement asks the
  researcher which they mean.

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
- **Explanation.** The template is the default. With `DD_POLICY_EXPLAINER=model`, a model
  writes the rationale only, from `system_prompt.md`. It is sent registry text and the context,
  never research data.

## Configuration

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
  for embargoes or for when data must be shared, so those obligations are always `unstated`.
  TODO(#302)
- The FAIRsharing API returns no relations from a policy to the databases and standards it
  names, even for policies that list repositories on the website. So the repository and standard
  obligations are `unstated`, and `mandated_repositories` is empty, until a route provides them.
  An empty list is not evidence that no repository is mandated, and the statement says so,
  naming the actors with no record as unchecked. TODO(#302, #331)
- An actor is matched by name, and only to a record whose name contains one of its names. A
  funder is searched by every name ROR gives it, but a journal or institution only by the name
  given. ROR's live search reads the first page of results only, so a common name may need the
  dump or the identifier.
- A funder's affiliation country does not yet rank its ROR candidates.
- Differences are found between strengths only. Two policies that require different
  repositories are not yet compared. TODO(#331)
- The FAIRsharing client is a copy of the standards advisor's, since an agent may not import
  another ([System and boundaries](../../docs/specs/system.md)). TODO(#280)
