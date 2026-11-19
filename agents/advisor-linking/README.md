# advisor.linking

**Alpha** (`0.2.0a1`, [Agents](../../docs/specs/agents.md)). It checks the form of identifiers and,
where the deployment grants it a DOI source, looks DOIs up. A model writes only a summary beside
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
- `resolved`, `title` and `resource_type`: for a DOI looked up, whether it was found and, if so,
  the record's title and type; `resolved` is absent where no lookup was made;
- `message`: what to check or how to record it, or why a lookup failed.

It also gives a `summary` (below) and lists, in `limitations`, what it did not do.

## How it decides

Each identifier is matched against `schemes.yaml`, in order: DOI, ORCID iD, ROR id
(`0` followed by six letters or digits and two digits), then grant number. An ORCID iD's last
character must be its ISO 7064 MOD 11-2 checksum. A string is taken for a grant number only when
it matches no other scheme, has no spaces or colons and contains a digit; anything else is
`unknown`. With no identifiers it abstains (`insufficient_input`). This part is exact and uses no
source.

## Resolving DOIs

Which sources exist is the deployment's choice: it lists the MCP servers it runs, and its profile
grants them to `advisor.linking` (`tool_servers`). The adviser declares the servers `crossref` and
`datacite`, each with the tool `get_doi`; of those the gateway lists for the invocation, it calls
the first that offers `get_doi`, with `{"doi": "<bare DOI>"}`. The tool returns one structured
record with a `title` and a `type`, and the harness records it. The adviser puts those on the link
and cites the record in `grounded_on` and in the evidence (`dd_sdk.tools.ToolRecord`). The code is
in `resolve.py`. No such server is in this repository.

A lookup that errors, fails or finds nothing is never raised: the link says `resolved: false`, with
the reason in `message`. With no grant, or no such tool listed, no DOI is looked up and
`limitations` says so.

Its grounding mode is `retrieval`. A run that looked nothing up cites its input, which the adviser
reads itself and records with its own retrieval span, since the rules for `retrieval` accept
nothing without one.

## What it does not do

- It resolves ORCID iDs, ROR ids and grant numbers by form only, so a well-formed one may not
  exist or may name something else; `limitations` says so on every run.
- It does not look up names, funders or relations in ORCID, ROR or funder services, and its
  relation suggestions are defaults by scheme.
- It recognises no other identifier, such as an arXiv id or an accession number.

Resolving those identifiers is TODO(#360).

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
