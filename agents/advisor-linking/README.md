# advisor.linking

**Alpha** (`0.2.0a1`, [Agents](../../docs/specs/agents.md)). It checks the form of identifiers and,
where the deployment grants it lookup tools, looks DOIs, ORCID iDs and ROR ids up. A model writes only a summary beside
its findings.

The Linking Adviser helps a researcher link a dataset to the publications, people, organisations,
grants and software around it (Blueprint R11), with persistent identifiers in a form ready for
metadata (R7). It serves two steps of the Blueprint's process flow (§8.2):

| Step | What it does |
|---|---|
| `deposit.links` | Suggests how to record each identifier in the dataset's DataCite metadata before deposit. |
| `post.links` | The same, for links added after publication. |

It produces linking metadata for the researcher to review. Registering the links stays with the
researcher and the repository.

## Input and output

`LinkCandidates` gives `identifiers`, each as the researcher wrote it. `RelatedIdentifiers` holds
one `RelatedLink` per identifier, with:

- `scheme`: `doi`, `orcid`, `ror`, `grant` or `unknown`;
- `normalised`: the canonical https form of a DOI, ORCID iD or ROR id;
- `relation`: a suggested DataCite relationType (`IsSupplementTo` for a DOI), absent where the
  adviser cannot tell;
- `valid`: whether the identifier is well formed for its scheme;
- `resolved`, `title` and `resource_type`: for a DOI, ORCID iD or ROR id looked up, whether it
  was found and, if so, what it names: a DOI's title and type, a person's name, or an
  organisation's name and type; `resolved` is absent where no lookup was made;
- `message`: what to check or how to record it, or why a lookup failed.

It also gives a `summary` (below) and lists, in `limitations`, what it did not do.

## How it decides

Each identifier is matched against `schemes.yaml`, in order: DOI, ORCID iD, ROR id
(`0` followed by six letters or digits and two digits), then grant number. An ORCID iD's last
character must be its ISO 7064 MOD 11-2 checksum. A string is taken for a grant number only when
it matches no other scheme, has no spaces or colons and contains a digit; anything else is
`unknown`. With no identifiers it abstains (`insufficient_input`). This part is exact and uses no
source.

## Resolving DOIs, ORCID iDs and ROR ids

Which sources exist is the deployment's choice: it lists the MCP servers it runs, and its profile
grants them to `advisor.linking` (`tool_servers`). In this repository they are the PID resolver's
([`mcp-pid/README.md`](../../mcp-pid/README.md)); in development, `pid_resolver: true` in
`deployment.yaml` runs and grants them. The adviser declares, for each scheme, the servers to ask
in order and the one tool each offers:

| Scheme | Asked of | Tool | Puts on the link |
|---|---|---|---|
| DOI | `datacite`, then `crossref` | `get_doi` | the title and resource type |
| ORCID iD | `orcid` | `get_orcid` | the person's public name, and `Person` |
| ROR id | `ror` | `get_organisation` | the organisation's name and its first ROR type |

Each tool answers `{"records": [...]}`: one record when found, none when not. A DOI DataCite did
not register is asked of Crossref. The harness records each record; the adviser cites the one each
link was resolved against in `grounded_on` and in the evidence (`dd_sdk.tools.ToolRecord`). The
code is in `resolve.py`.

A lookup that errors, fails or finds nothing is never raised: the link says `resolved: false`, with
the reason in `message`. A scheme with no granted tool is checked by form only, and `limitations`
names it.

Its grounding mode is `retrieval`. A run that looked nothing up cites its input, which the adviser
reads itself and records with its own retrieval span, since the rules for `retrieval` accept
nothing without one.

## What it does not do

- It checks grant numbers by form only, so a well-formed one may not exist or may belong to
  another funder; `limitations` says so on every run. Resolving them is TODO(#953).
- It does not look up funders or the relations between works, and its relation suggestions are
  defaults by scheme.
- It recognises no other identifier, such as an arXiv id or an accession number.

## Summary

A summariser (`dd_sdk.summary`) writes a short `summary` beside the findings, with
`summary_derivation` saying how it came about. `DD_LINKING_SUMMARISER` (`factory.py`,
`config/examples/agents.env`) chooses it:

- `model` (default): a model is sent the findings (each identifier as given and what was found for it) and writes the summary from
  `system_prompt.md`. A reply that is missing, refused, or names a DOI, ORCID iD or web address
  the findings do not give is replaced by the rules' own summary, marked `template`, as is a
  model that cannot be reached. The model and its key are set as for every agent
  ([AI models](../../docs/guide/operations/ai-models.md)). Left unset with no key, `dd.py start`
  runs it with `template`.
- `template`: the rules' own summary; calls no model and needs no key.

The model changes no finding: each link is recognised, checked and looked up by the rules above either way.
