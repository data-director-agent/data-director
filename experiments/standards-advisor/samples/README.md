# Sample dataset

`soil-chemistry.csv` and its metadata record are **hand-written for this repository**. They are
not harvested from FAIRsharing, not downloaded from FigShare or Zenodo, and not derived from any
registry content — so no CC-BY-SA share-alike obligation is carried onto anything published from
here (§7.4).

The columns are chosen to exercise every branch of the §5.1 tier-1 column type inference:

| Column | Exercises |
|---|---|
| `sample_id` | identifier |
| `collection_date` | ISO 8601 date |
| `sampled_at` | ISO 8601 date-time with offset |
| `survey_date_uk` | a non-ISO date format — the case R3.4 exists for |
| `latitude`, `longitude` | coordinates |
| `soil_horizon`, `land_use` | low-cardinality categorical |
| `ph` | plain number |
| `organic_carbon_pct`, `bulk_density_g_cm3` | number with units in the column name |
| `total_nitrogen` | plain number, no unit in the header |
| `notes` | free text, 80% blank — exercises the blank-proportion count |
| `analyst_orcid` | identifier (ORCID) |

Two of those are precedence tests rather than simple cases. `analyst_orcid` has only three
distinct values across forty rows, so cardinality alone would call it categorical; the ORCID
pattern has to win, or R3.1 would be offered a vocabulary for a column of author identifiers.
And `soil_horizon` (`O`/`A`/`B`) must *not* be caught by the accession-identifier pattern, which
is why that pattern requires a separator.

`survey_date_uk` is deliberately ambiguous day/month order in some rows and not others. A
profiler that reports it as a date without recording *which* format matched is hiding the thing
R3.4 needs to know.
