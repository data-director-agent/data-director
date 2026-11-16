# advisor.policy

**Alpha** (`0.1.0-alpha`): exploratory, and likely to change shape.

The policy advisor checks what the data and open access policies of a project's funders, journals
and institution ask of it. It serves two steps of the Blueprint's process flow (§8.2):

| Step | What the agent does |
|---|---|
| `governance.policies` (Phase 2, Figure 2) | Matches each funder, journal and institution to its policy records in FAIRsharing and Jisc Open Policy Finder, and reports what each asks, quoted from the record, and where they differ. |
| `repository.mandated` (Phase 3, Figure 3) | Reports the repositories a matched policy requires, in the form `advisor.repository` takes as `RepositoryNeeds.mandated`. |

The guidance note to Figure 2 suggests FAIRsharing's policy records as the source. They are
curated summaries, and many funders and publishers have none (#750, #905), so the agent also
reads [Jisc Open Policy Finder](https://openpolicyfinder.jisc.ac.uk), which replaced Sherpa
Romeo and Juliet, and asks Crossref which publisher a journal belongs to. By default a model then
reads the records found, searches for more, and states what each policy asks, each obligation
with a quote that the agent checks is in the record. Records are still summaries of the policies,
so every result needs a person to check it against the policy text. The agent flags where policies
differ and never decides which applies.

## Input and output

`PolicyContext` names the actors, each a `funder`, `journal` or `institution` with a name and,
when known, the FAIRsharing identifier of its policy. A funder may also carry its ROR identifier
(`ror_id`), and a journal its ISSN (`issn`), which is how the researcher answers when a name is
ambiguous. It may also give the disciplines, the kinds of data and the publication date.

`PolicyChecks` holds:

- `policies`: one entry per policy record matched to an actor, with the `registry` it came from
  (`fairsharing` or `open_policy_finder`) and `match_derivation`: `registry` when the first
  search's rule matched it, `model` when a model found it with its tools. The record is named only
  in `grounded_on`; its name, clauses and policies are the evidence `content`
  ([Evidence and grounding](../../docs/specs/grounding.md)). Each obligation (`deposit`,
  `data_availability_statement`, `repository`, `standard`, `embargo`, `licence`, `timing`) is
  `required`, `recommended` or `unstated`, with its `scope` (`data`, or `publication` for an
  article's open access terms) and its `derivation`. One read by rule from a FAIRsharing record
  keeps the curators' value in `recorded_as`; one a model read has `value` and `quote`, the
  record's own words. Each entry also has notes and a rationale.
- `conflicts`: each kind of obligation that matched policies state with different strengths,
  within one scope, grounded on every policy involved.
- `mandated_repositories`: the repositories a matched policy requires.
- `no_record`: the actors with no policy record.
- `funders`: each funder identified in ROR, grounded on its ROR record (the identifier is stated
  there only), with the Crossref Funder ID ROR prefers, so that both can be passed on.
- `journals`: each journal identified, with its publisher and ISSN, grounded on its Open Policy
  Finder or Crossref record.
- `ambiguous`: each funder whose name could mean more than one organisation in ROR, and each
  journal title that could mean more than one journal, grounded on every candidate, likeliest
  first. Its policy was not looked up, and the statement asks the researcher which they mean.

## How it decides

Retrieval comes first, by fixed rules. A model, when there is one, comes after, and its word is
never taken alone:

- **Identifying funders** (`resolve.py`, `ror.py`). Each funder is looked up in ROR, by its ROR
  identifier when given, otherwise by an exact match, ignoring case and spacing, against every
  name, acronym and alias ROR records for an active organisation. One match is resolved, and
  FAIRsharing is searched by each of its English names as well as the name given. More than one
  is not guessed: the candidates are returned and the researcher is asked, funders and
  organisations with a Crossref Funder ID shown first. A name such as "UKRI-NERC" that ROR does
  not hold is read through ROR's own parent relationships. No alias table is kept. When ROR
  cannot be read, funders are searched by the name given and the statement says so.
- **Identifying journals** (`discover.py`, `opf.py`, `crossref.py`). A journal is read from Open
  Policy Finder by its ISSN when given, otherwise searched by its title, and kept only when the
  title is the same once case, punctuation, "&" and a leading "The" are set aside. Two journals
  with that title are not guessed between: the researcher is asked for the ISSN. Open Policy
  Finder links the journal to its publishers; when it has no record of the journal, Crossref's
  journals API names the publisher. The publisher's name, with any legal form such as "BV" set
  aside, is then searched in FAIRsharing too, so a journal with no policy of its own reaches its
  publisher's (#905). No table of publishers is kept.
- **Open Policy Finder** (`discover.py`). Each funder is searched by every name ROR gives it, and a
  record kept when one of its names or acronyms contains one of those names as whole words. A
  journal's own record is kept, or its publisher's when Open Policy Finder has none for the
  journal. Without a key it is not searched, and the statement says so; when it cannot be asked,
  the statement says so and FAIRsharing still answers.
- **Matching** (`match.py`). An actor given with a FAIRsharing identifier is fetched by it.
  Otherwise each of its names is searched, and a record is kept only when FAIRsharing types it for the
  actor's role (a journal matches a journal or journal publisher policy) and its name or
  abbreviation contains one of those names as whole words. At most three records are kept per
  actor, shortest name first, so a publisher's own policy comes before its journals'.
- **Obligations by rule** (`assess.py`). Read from FAIRsharing's curated fields by fixed rules: `deposit` from
  `sharing_data.mandated_data_sharing`, `data_availability_statement` and `licence` from their
  `required` values, and `repository` and `standard` from the record's `requires` and
  `recommends` relations. `required` and `yes` give `required`; `suggested` and `recommended`
  give `recommended`; anything else gives `unstated`. A value such as `no` is kept in
  `recorded_as`, since a record that says a policy does not require something is not the same as
  one that says nothing.
- **Notes**. The agent notes a policy whose subjects do not include the discipline, a policy
  dated after the publication, a policy that allows exceptions to sharing, and a required data
  management plan.
- **The model advisor** (`advise.py`, `verify.py`; the default). A model is given the context and
  every record the first search retrieved, numbered `R1`, `R2`… and marked as untrusted data
  (`system_prompt.md`). It may search Open Policy Finder, Crossref and FAIRsharing with read-only
  tools, at most `DD_POLICY_MAX_LOOKUPS` times a run; each record a tool returns is retrieved by
  the agent and numbered in turn. It ends by calling `submit_findings` with, for each record that
  applies to an actor, a rationale and the obligations the record states, each with a quote. The
  agent then keeps:
  - an obligation only if its quote, at least three words long, is in the record it names, once
    case, spacing, quotation marks and dashes are set aside;
  - a record a tool found only if it is a policy of the actor's kind (a funder's for a funder, a
    journal's or publisher's for a journal), for an actor the researcher named whose name was not
    ambiguous, at most three per actor, marked `match_derivation: model` with a note to check it;
  - every policy the first search matched and every obligation read by rule. A model's claim
    fills an obligation the record left `unstated`, or adds one about the publication; where it
    disagrees with a curated value, the curated value is kept and the difference is noted.

  What is dropped, and why, is in the statement. If the model declines, cannot be reached, or
  submits no findings, the template is used and the statement says so. The model is sent
  registry text and the context, never research data.
- **Template** (`explain.py`, `DD_POLICY_ADVISOR=template`). The rationale is written from a
  template, and obligations are only those read by rule.
- **Conflicts**. When matched policies state the same kind of obligation with different
  strengths, such as a funder requiring deposit where the institution only recommends it, the
  difference is listed for a person to resolve. Data and publication obligations are compared
  separately.

## Configuration

- `DD_POLICY_RETRIEVAL`: `snapshot` (the default) or `live`. Live search needs a FAIRsharing
  account: `FAIRSHARING_LOGIN`, and `FAIRSHARING_PASSWORD` or `FAIRSHARING_PASSWORD_FILE`.
  `uv run scripts/dd.py setup` writes them when it is given a login. With `live`, the agent
  falls back to the snapshot, marked stale, when the route fails.
- `DD_POLICY_ROR`: `snapshot` (the default) reads the ROR registry built from its pinned dump;
  `live` asks `api.ror.org`, which needs no account, and falls back to that registry, marked
  stale, when the route fails.
- `DD_POLICY_ADVISOR`: `model` (the default) or `template`. `model` needs the provider, model
  and key as for the standards advisor ([AI models](../../docs/guide/operations/ai-models.md),
  [Policy and identity](../../docs/specs/policy-and-identity.md)); with it unset and no key, the
  agent stops at start-up and says to set `template`, and `uv run scripts/dd.py start` runs it
  with `template`. `DD_POLICY_EXPLAINER` is its older name and still works.
- `DD_POLICY_MAX_LOOKUPS`: the most searches the model may make in one run, from 0 to 30 (6 by
  default).
- `OPEN_POLICY_FINDER_API_KEY` or `OPEN_POLICY_FINDER_API_KEY_FILE`: a free key from
  [Open Policy Finder](https://openpolicyfinder.jisc.ac.uk/help/developers/how-to-request-a-new-api-key).
  On a VM: `sudo data-director secret set advisor-policy open-policy-finder-api-key`.
- `DD_POLICY_CROSSREF`: `live` (the default) asks Crossref which publisher a journal belongs to;
  `off` does not.

## Sources

`data/fairsharing/` holds the committed snapshot, one record per line in the form that is hashed.
Its label, `fairsharing-policy:snapshot:<date>`, differs from the repository advisor's copy of
FAIRsharing's database records. It is pinned in `workbench/sources.yaml` and
`app/config/sources.yaml`, so the harness's source check verifies the evidence against it
([Agents](../../docs/specs/agents.md)). The identifiers kept are listed in `data/fairsharing/ids.txt`. To rebuild, run
`uv run python agents/advisor-policy/scripts/build_policy_snapshot.py` with the FAIRsharing login set, then pin
the new file.

Open Policy Finder (`api.openpolicyfinder.jisc.ac.uk`, key in the `x-api-key` header) and
Crossref's journals API are read live only, labelled `open-policy-finder:live:<date>` and
`crossref-journals:live:<date>`. Jisc states no licence for the records that would let a copy be
committed, nor a rate limit (#952). To check the route with a key, run
`uv run python -m dd_agent_advisor_policy.opf check`; `--record <folder>` writes what came back,
for the test fixtures.

`data/ror/` pins one ROR data dump (CC0; see `data/ror/SOURCE.md`). The registry built from it
is not committed: `uv run dd-sources prepare` builds it, as it builds the re3data registry, and
its label is `ror:dump:<version>`. `uv run dd-ror fetch --update-pin` pins the newest dump.

## Limits

- FAIRsharing's policy records are coarse, and many institutions have none. They have no field
  for embargoes or for when data must be shared; a model can read these from a record's text
  only where the record states them. The policies' own pages are not read. TODO(#904)
- Open Policy Finder's client was written from Jisc's documentation and the Sherpa v2 API's shape,
  without a key: the `funder` item type, the filter fields and the answer's shape are still to be
  confirmed, and the test fixtures are hand-written. TODO(#302)
- Open Policy Finder mostly states open access policy for articles, not data policy. Its
  obligations are marked `scope: publication` unless the text is about data.
- A quote shows that the record says it; it does not show that the model read it rightly. Each
  model-read obligation is marked as such, and a person should check it against the quote.
- The model's tools reach the registries from this agent, not through the harness's tool
  gateway. TODO(#875)
- The FAIRsharing API returns no relations from a policy to the databases and standards it
  names, even for policies that list repositories on the website. So the repository and standard
  obligations are `unstated`, and `mandated_repositories` is empty, until a route provides them.
  An empty list is not evidence that no repository is mandated, and the statement says so,
  naming the actors with no record as unchecked. TODO(#302, #331)
- An actor is matched by rule by name, and only to a record whose name contains one of its
  names. A funder is searched by every name ROR gives it, a journal also by its publisher's, and
  an institution only by the name given. ROR's live search reads the first page of results only, so a common name may need the
  dump or the identifier.
- A funder's affiliation country does not yet rank its ROR candidates.
- Differences are found between strengths only. Two policies that require different
  repositories are not yet compared. TODO(#331)
- The FAIRsharing client is a copy of the standards advisor's, since an agent may not import
  another ([System and boundaries](../../docs/specs/system.md)). TODO(#280)

## Reading the policy's own text

The registries' records are curated summaries and say little of which repository, by when, for
how long data may be withheld or under which licence. So each policy's own text is read as well
(`policy_text.py`, `pdf_text.py`, `extract.py`):

- Each matched FAIRsharing record's `homepage`, and each `policy_url` an actor carries, is fetched
  once. HTML becomes text without scripts, styles, navigation, header and footer; a PDF is read
  with `pypdf`; anything else is unreadable. A short landing page that links to PDFs on its own
  site has up to two of them read with it. Every page is fetched before any model is called.
- A model is given the text, as quoted data in the user turn, and returns each obligation it
  finds, with its kind, strength, value and the passage that says so.
- The code keeps an obligation only if its quote is in the text, word for word once typography and
  white space are made plain, and at least twenty characters long. It drops the rest and says why
  in `dropped`.
- The result is `readings` in the payload, one per page, grounded on the text (cited by its
  address, with the whole text as the evidence `content`) and on the record it was reached from.
  Readings sit beside a record's obligations and never change them; where the two differ, both are
  shown and the statement says so.
- The `policy_text` setting is `read` by default; the institutional profile may set it to `off`
  (`agent_settings`, docs/specs/policy-and-identity.md). Reading needs a model: the advisor's, or
  the one the agent's settings configure. With none, nothing is fetched and the statement says so.

Limits: a page is read only where a matched FAIRsharing record names it or the researcher gives a
`policy_url`; Open Policy Finder records name an organisation's home page, not its policy, so
they are not fetched. A page is read as it is when fetched, which may not be the version that
applied at the publication date, and only its first 60,000 characters (or 60 PDF pages) are read.
Pages are read live and not pinned, so the source check reports them as unresolved. Repositories
the text requires are in `readings` and the statement; they are not yet passed to
`advisor.repository` as mandated (#753). No run with a real model has measured how accurate the
readings are.
