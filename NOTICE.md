# Notice

The code in this repository is under the [MIT licence](LICENSE), copyright The University of
Sheffield. That licence covers the code only. This file says what it does not cover.

## Data and services under their own terms

Each copy of a source's data is kept with its licence file (`LICENCE.md` or `SOURCE.md`). The app
credits each source on its Sources and licences page, from [`app/config/credits.yaml`](app/config/credits.yaml).

| Source | Licence | Used as | Where |
|---|---|---|---|
| [FAIRsharing](https://fairsharing.org) | CC BY-SA 4.0 | Snapshots, and the live API | `agents/advisor-{standards,repository,policy}/data/fairsharing/` |
| [re3data](https://www.re3data.org) | CC0 1.0 | A pinned export, built locally and not committed | `agents/advisor-repository/data/re3data/` |
| DataCite repositories | CC0 1.0 | Snapshot | `agents/advisor-repository/data/datacite/` |
| [ROR](https://ror.org) | CC0 1.0 | A pinned dump, built locally and not committed | `agents/advisor-policy/data/ror/` |
| [OpenAlex](https://openalex.org) | CC0 1.0 | A pinned snapshot, built locally and not committed | `journals/src/dd_journals/data/` |
| [PRONOM](https://www.nationalarchives.gov.uk/PRONOM/) | Open Government Licence v3.0 | Signatures and records | `inventory/src/dd_inventory/pronom/`, `formats/src/dd_formats/data/` |
| [SPDX License List](https://spdx.org/licenses/) | CC0 1.0 | Pinned list | `mcp-spdx/src/dd_mcp_spdx/data/` |
| [GA4GH Data Use Ontology](https://github.com/EBISPOT/DUO) | CC BY 4.0 | Pinned terms | `duo/src/dd_duo/data/` |
| [UCUM](https://ucum.org) | UCUM Copyright Notice and License | The unit table, through `ucumvert` | `units/README.md` |
| ANZSRC 2020 Fields of Research | CC BY 4.0 | Classification | `subjects/src/dd_subjects/data/` |
| OECD Fields of R&D | OECD excerpt terms, with acknowledgement | Classification | `subjects/src/dd_subjects/data/` |
| [Inter](https://rsms.me/inter/) typeface | SIL Open Font License 1.1 | Bundled in the app's shell | `app/web` |
| DataCite and Crossref REST, ORCID, OpenAIRE Graph, DOAJ, Jisc Open Policy Finder | Each service's own terms | Asked live; nothing kept | [Dependencies](docs/specs/dependencies.md) |

Four terms bind a reuse of this repository more tightly than MIT does:

- **FAIRsharing, CC BY-SA 4.0.** The snapshot files, and anything copied out of them, carry
  attribution and the same licence. The test fixtures and recorded responses that hold FAIRsharing
  records (`agents/*/tests/`, `mcp-fairsharing/tests/`, `app/web/fixtures/` and
  `app/web/cassettes/`) are under it too. Whether an agent's output built from FAIRsharing records
  is an adaptation under that licence is a legal question this project has not settled; ask your
  institution's information compliance or legal team before publishing such output.
- **Jisc Open Policy Finder, CC BY-NC-ND 4.0, API for non-commercial use.** It is asked live and
  never kept, because no-derivatives rules out a copy.
- **ORCID's public API** is licensed for non-commercial use. Nothing from it is kept.
- **OpenAIRE Graph, CC BY 4.0, and the DUO and ANZSRC data, CC BY 4.0,** must be credited.

A deployment that is not a non-commercial research institution's must read those terms before it
turns the sources on.

## Text

`docs/blueprint/` is the RDA Data Director Agentic AI Blueprint, reproduced under CC BY 4.0
([doi:10.15497/RDA00157](https://doi.org/10.15497/RDA00157)). The MIT licence does not cover it.

## Other third-party material

The icons in the app are Lucide (ISC) and Octicons (MIT; licence in
`app/web/src/components/ui/brand-icons.LICENCE`). The ORCID iD icon is ORCID's trademark. The
XML Schemas the metadata tests validate against carry their own licences in
`metadata-records/tests/data/xsd/NOTICE.md`. Python and npm dependencies keep their own licences;
a policy on which are acceptable is not yet decided (TODO(#82)).

## What no one has checked

This notice was written without reading FAIRsharing's own terms of use
(`https://fairsharing.org/licence`), whose page could not be fetched as text. The credit it
records is what FAIRsharing's documentation and API responses state: CC BY-SA 4.0, an attribution
link and a badge. A person should read those terms, and correct this file and
`app/config/credits.yaml` if they say more, in particular about automated access, storing
responses and the attribution wording.
