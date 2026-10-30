# advisor.linking

**Alpha, and a mock** (`0.1.0a1`, ADR-0033). It does not give real advice: it checks the form of
identifiers and resolves none of them.

The Linking Adviser helps a researcher link a dataset to the publications, people, organisations,
grants and software around it (Blueprint R11), with persistent identifiers in a form ready for
metadata (R7). It serves two steps of the Blueprint's process flow (§8.2):

| Step | What the mock does |
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
  mock cannot tell;
- `valid`: whether the identifier is well formed for its scheme, and `message`: what to check or
  how to record it.

It also lists, in `limitations`, what the mock does not do.

## How it decides

Each identifier is matched against `schemes.yaml`, in order: DOI, ORCID iD, ROR id
(`0` followed by six letters or digits and two digits), then grant number. An ORCID iD's last
character must be its ISO 7064 MOD 11-2 checksum. A string is taken for a grant number only when
it matches no other scheme, has no spaces or colons and contains a digit; anything else is
`unknown`. With no identifiers it abstains (`insufficient_input`). Its grounding mode is `none`:
it cites only its input.

## What it does not do

- It resolves nothing and consults no source, so a well-formed identifier may not exist or may
  name something else.
- It does not look up titles, names, funders or relations in DOI, Crossref, DataCite, ORCID, ROR
  or funder services, and its relation suggestions are defaults by scheme.
- It recognises no other identifier, such as an arXiv id or an accession number.

The real adviser, which resolves identifiers through those services, is TODO(#360).
