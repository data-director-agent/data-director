# dd-dmp-template

The core requirements for a Data Management Plan (DMP), after Science Europe's.

```python
>>> from dd_dmp_template import SECTIONS
>>> [s.heading for s in SECTIONS][:2]
['Data description and collection', 'Documentation and data quality']
```

It is contract-free: it imports no other Data Director package and nothing outside the standard
library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The Documentation Editor drafts a plan to its
sections, and the Data Management Planner has a model review an attached plan against
their questions ([Drafting documents](../docs/specs/drafting.md), [`advisor.dmp`](../agents/advisor-dmp/README.md)).

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

Each has a one-sentence `summary` a researcher can answer, and its `questions` in this library's
own paraphrase of the guide's. Two questions are not the guide's but this library's additions,
after the [STFC/UKRI](https://www.ukri.org/councils/stfc/guidance-for-applicants/what-to-include-in-your-proposal/data-management-plan/)
and [UK Data Service](https://ukdataservice.ac.uk/learning-hub/data-producer-support/planning-and-governing-research-data/planning/data-management-planning/)
guidance: how long the data will be kept (`sharing-preservation`), and how and when the plan
will be reviewed and updated, and by whom (`responsibilities-resources`). A plan is a living
document, kept up to date as the research proceeds.

## Honest limits

- It holds the requirements only. It does not read a plan: whether a plan answers them is for a
  person, or a model whose reading a person checks. A plan's headings say little about that, so no
  rule here matches them.
- It is one funder-neutral template. A funder's own template (UKRI's councils', Horizon
  Europe's) asks more, or in another order.

## Credit

The six requirements and their questions follow Science Europe's guide, published under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the wording here is a paraphrase. The
questions on retention and on keeping the plan up to date follow the STFC/UKRI and UK Data
Service guidance.
