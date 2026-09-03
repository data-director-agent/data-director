# Sample planned dataset (§8)

`README.md`, `soil-survey.dictionary.json` and `answers.json` are **hand-written for this
repository**, like `samples/soil-chemistry.*`. They are not harvested from FAIRsharing, not
downloaded from FigShare or Zenodo, and not derived from any registry content — so no CC-BY-SA
share-alike obligation is carried onto anything published from here (§7.4).

They stand in for the output of **R5** at Blueprint Phase 1: a README and a draft data dictionary
written before any data exists. R5 is out of scope for this experiment; this is what its output
would look like arriving at R3's door.

## What the dictionary exercises

The fields are chosen to cover every branch of `planning/dictionary.py`, including the ones that
refuse to answer.

| Field | Declared type | Exercises |
|---|---|---|
| `plot_id` | `string` / `uuid` | string format promoted to `identifier` |
| `survey_date` | `date` / `%d/%m/%Y` | **a declared non-ISO date** — the case R3.4 exists for, and a pattern tier 1 recognises |
| `survey_start_time` | `time` | `TIME`, and the `default` format filled in from the standard |
| `survey_duration` | `duration` | `DURATION` — ISO 8601 has an answer and researchers rarely use it |
| `survey_year` | `year` | a coarse date, mapped to `DATE` with pattern `%Y` |
| `latitude`, `longitude` | `number` | coordinate detection from the *name*, since the declared type is only `number` |
| `soil_horizon` | `string` + `enum` | a declared enumeration → `categorical`, R3.1's target |
| `restoration_treatment` | `string` + `enum` | a longer enumeration, and the R3.1 case with no obvious vocabulary |
| `ph` | `number` | a plain number with no unit anywhere |
| `organic_carbon_pct` | `number` | **unit from the column name**, since Table Schema has no `unit` |
| `total_nitrogen` | `number` + `unit` | unit *declared* outright — the stronger derivation |
| `sward_height_cm` | `number` | another name-derived unit, on a variable with no ISO answer |
| `waterlogged` | `boolean` | `BOOLEAN` — how true and false get written down |
| `quadrat_species_cover` | `object` | **the refusal path.** No `ColumnType` fits, so it becomes `unknown`, a failure records why, and no field-level search runs for it |
| `surveyor_notes` | `string` | free text, the fallback |

Two of those are precedence tests rather than simple cases. `soil_horizon` declares both a type
and an enumeration, and the enumeration has to win — a coded field needs a vocabulary far more
than it needs a string format. And `latitude` declares `number`, so the coordinate conclusion can
only come from the column name; a mapping that trusted the declared type alone would offer it a
number format instead of ISO 6709.

`quadrat_species_cover` is the important one. Filing it as free text and recommending a text
standard would be worse than saying nothing, which is why `read_dictionary` reports it and
`retrieve.FIELD_LEVEL_TYPES` excludes `unknown`.

## `answers.json`

The intake answers (§8) that `elicit` would otherwise pause to ask for, so the sample run is
non-interactive and the test suite never has to drive an interrupt to exercise the rest of the
pipeline.

`target_repository` is deliberately an empty list. Pre-collection that is the honest answer far
more often than not — the Blueprint puts repository selection in Phase 3 — and it exercises the
skipped-answer path, which must be recorded as *skipped* rather than as never asked.
