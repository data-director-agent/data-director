# dd-dmp-template

The core requirements for a Data Management Plan (DMP), after Science Europe's, and a rule that
finds which of them a plan's headings cover.

```python
>>> from dd_dmp_template import SECTIONS, coverage
>>> [s.heading for s in SECTIONS][:2]
['Data description and collection', 'Documentation and data quality']
>>> [(c.section.id, c.covered) for c in coverage("## Storage and backup\nNightly.")][2]
('storage-backup', True)
```

It is contract-free: it imports no other Data Director package and nothing outside the standard
library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The Documentation Editor drafts a plan to its
sections, and the Data Management Plan Checker reviews an attached plan against them
([Drafting documents](../docs/specs/drafting.md), [`advisor.dmp`](../agents/advisor-dmp/README.md)).

## The sections

`SECTIONS` holds the six core requirements of Science Europe's
[*Practical Guide to the International Alignment of Research Data Management*](https://doi.org/10.5281/zenodo.4915862)
(extended edition, 2021), which most funders' templates map onto:

| `id` | Heading |
|---|---|
| `data-collection` | Data description and collection |
| `documentation-quality` | Documentation and data quality |
| `storage-backup` | Storage and backup during the project |
| `legal-ethical` | Legal and ethical requirements |
| `sharing-preservation` | Data sharing and long-term preservation |
| `responsibilities-resources` | Responsibilities and resources |

Each has a one-sentence `summary` a researcher can answer, its `questions` in this library's own
paraphrase of the guide's, and the `cues`, words a plan's heading for it commonly uses.

## Coverage

`split(text)` cuts a plan into passages at its headings: a Markdown heading, a numbered line
(`3. Storage`, `3.1 Backup`) or a line in bold alone. `coverage(text)` gives, for each section,
the passages whose heading holds one of its cues. A heading may name several sections.

## Honest limits

- It reads headings only. A covered section may still leave its questions unanswered, and a plan
  that answers them under other headings, or with none, is reported as not covering them. A
  person, or a model whose reading a person checks, judges the content.
- The cues are English, and chosen by hand from common templates; there is no evaluation of how
  often they miss.
- It is one funder-neutral template. A funder's own template (UKRI's councils', Horizon
  Europe's) asks more, or in another order.

## Credit

The six requirements and their questions follow Science Europe's guide, published under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the wording here is a paraphrase.
