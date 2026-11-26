# Sources and licences

Data Director's code is under the MIT licence. The data, registries and services its agents read
belong to their publishers (see also [Acknowledgements](acknowledgements.md)). Each stays under its own licence and terms, and the app credits it as
its publisher asks.

## Where the credit is shown

- **The Sources and licences page** (`/sources` in the app, linked from every page's footer, and
  open without signing in) lists each source, the credit it asks for, its licence, whether a copy is
  kept or it is asked at run time, and a link to its terms. A source whose terms are limited to
  non-commercial use is marked.
- **The evidence panel** of a run names the source of each record an agent cited and its licence,
  linking to the page.
- **[NOTICE.md](../../../NOTICE.md)** in the repository lists the same sources with where each
  copy is kept, and the terms that bind a reuse more tightly than MIT does.
- **Each copy of data** is kept with its own `LICENCE.md` or `SOURCE.md`.
- **[CITATION.cff](../../../CITATION.cff)** cites the sources that ask to be cited.

## What each source asks

| Source | Licence | What it asks |
|---|---|---|
| FAIRsharing | CC BY-SA 4.0 | Attribution with a link to <https://fairsharing.org> and its badge; anything adapted from it stays CC BY-SA 4.0. Its REST API needs an account. |
| re3data, DataCite, ROR, OpenAlex, SPDX, DOAJ | CC0 1.0 | Nothing. Each is credited anyway. |
| PRONOM | Open Government Licence v3.0 | The statement "Contains public sector information licensed under the Open Government Licence v3.0." |
| GA4GH DUO, ANZSRC, OpenAIRE Graph | CC BY 4.0 | Credit to the source. |
| OECD Fields of R&D | Excerpt terms | Acknowledgement of the OECD as source and copyright owner. |
| UCUM | UCUM licence | Its copyright notice, and no change to the table. |
| ORCID public API | Non-commercial use | Use for non-commercial purposes only. |
| Jisc Open Policy Finder | CC BY-NC-ND 4.0; API for non-commercial use | Non-commercial use only; no copy is kept, and no adaptation made. |
| Inter typeface | SIL Open Font License 1.1 | Its copyright and licence notice stay with the font. |

The wording of each credit is in [`app/config/credits.yaml`](../../../app/config/credits.yaml).

## What a deployment must decide

- **Non-commercial sources.** ORCID's public API and Open Policy Finder are for non-commercial use.
  A university or other non-commercial research institution may use them. A deployment that is
  not one needs to read their terms, or leave those sources off. Profile control of this is not
  built yet.
- **FAIRsharing's ShareAlike condition.** Whether an agent's output that is built from FAIRsharing
  records is an adaptation under CC BY-SA 4.0 is a legal question this project has not settled.
  Ask the institution's information compliance or legal team before publishing such output. The
  records are attributed in the evidence either way.
- **FAIRsharing's own terms.** The project's notice records what FAIRsharing's documentation and
  API responses state. Read FAIRsharing's [licence page](https://fairsharing.org/licence) for
  automated access, storing responses and the attribution wording, and report any difference.
  The shared automated account FAIRsharing should agree to before a public deployment is
  tracked in #280.
- **Hosted model providers.** Their terms apply to what is sent and what comes back; see
  [AI models](../operations/ai-models.md).

## Adding a source

1. Keep a copy, if one is kept, with its licence file beside it.
2. Add a row to the external sources register in
   [Dependencies](../../specs/dependencies.md).
3. Add an entry to `app/config/credits.yaml`, with the credit in the publisher's own words and the
   prefixes that mark its evidence. `scripts/tests/test_credits_register.py` fails until the register and the
   file agree.
4. Add it to [NOTICE.md](../../../NOTICE.md), and to `CITATION.cff` if it asks to be cited.
