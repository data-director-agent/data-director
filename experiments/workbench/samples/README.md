# Sample inputs

| File | Purpose |
|---|---|
| `soil-chemistry.profile.json` | A `DatasetProfile` hand-derived from `experiments/standards-advisor/samples/soil-chemistry.metadata.json` and that CSV's header, so both experiments describe the same dataset. Exercises the succeeded path, including field-level (ISO 8601) recommendations. |
| `empty.profile.json` | No title, keywords, themes, media types or temporal fields: nothing to search on. Exercises `abstained(insufficient_input)`. |

Invoke with `uv run workbench invoke --agent r3.standards-advisor --input samples/soil-chemistry.profile.json`.
