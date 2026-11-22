# dd-subjects

Subject classifications that a person's field of study can be suggested from. Each scheme is a
published classification of fields of research, held as data with its source, version and
licence:

| Scheme id | Classification | Fields |
|---|---|---|
| `oecd-fos` | OECD Fields of Research and Development (formerly Fields of Science and Technology), Frascati Manual 2015, Table 2.2 | 6 broad fields, 42 second-level fields |
| `anzsrc-for` | ANZSRC 2020 Fields of Research, divisions and groups (release of 24 October 2025) | 23 divisions, 213 groups |

```python
>>> from dd_subjects import scheme, suggestions
>>> suggestions("oecd-fos")[:3]
['Natural sciences', 'Mathematics', 'Computer and information sciences']
>>> scheme("anzsrc-for").terms[1]
Term(code='3001', label='Agricultural biotechnology', parent='30')
```

`suggestions` gives a scheme's labels in code order, each broad field before the fields under
it, without repeats. They are suggestions: no scheme is a closed list of answers, and a person's
own words are always as good an answer. Different registries use different schemes (re3data the
DFG classification, many institutional repositories ANZSRC, FAIRsharing its own subject
ontology), so no one of them can be the required one.

It is contract-free: it imports no other Data Director package and nothing outside the standard
library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The model orchestrator uses it to suggest
answers when it asks for a researcher's discipline, from the scheme its `fields_of_study`
setting names ([Orchestration](../docs/specs/orchestration.md)).

## Sources and licences

The code is under the MIT licence (`LICENSE`). The data are the publishers', each file in
`src/dd_subjects/data/` naming its source, version, licence and attribution:

- **ANZSRC 2020 Fields of Research**, Table 2 of the Australian Bureau of Statistics' FoR
  workbook (`anzsrc2020_for.xlsx`, released 24 October 2025), © Commonwealth of Australia
  (Australian Bureau of Statistics) and Stats NZ, under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The workbook prints division
  titles in capitals; they are given here in sentence case, as the ABS's own text writes them.
  Group titles are as published.
- **OECD Fields of R&D**, Table 2.2 of OECD (2015), *Frascati Manual 2015: Guidelines for
  Collecting and Reporting Data on Research and Experimental Development*, OECD Publishing,
  Paris, <https://doi.org/10.1787/9789264239012-en>, © OECD 2015. The OECD's terms allow
  excerpts to be included in one's own documents and materials with acknowledgement of the
  source and copyright owner, and ask that requests for public or commercial use be sent to
  rights@oecd.org. The table's labels are reproduced here as such an excerpt, with that
  acknowledgement; the licence field reads `LicenseRef-OECD-excerpt` for that reason.

## Honest limits

- Labels only, in English; neither scheme's definitions or exclusions are included.
- ANZSRC's six-digit fields are left out: about 1,500 of them make a list to search, not to
  suggest from.
- No crosswalk between schemes, or to the DFG classification re3data uses
  ([#1407](https://github.com/data-director-agent/data-director/issues/1407)).

## Dependencies

None beyond Python 3.14's standard library.
