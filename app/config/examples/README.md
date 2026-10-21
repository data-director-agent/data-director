# Example inputs

The Run tab's **Load example** offers these. Each carries `schema_class`, and the shell lists an
example only for agents that accept that class. They are copies of the workbench's samples, held
here because the app must not depend on the workbench. TODO: agents should declare their own
examples (see the follow-up issue linked from #75), and this directory should then go.

| File | Class | Purpose |
|---|---|---|
| `soil-chemistry.profile.json` | `DatasetProfile` | R3's succeeded path, with field-level recommendations. |
| `empty.profile.json` | `DatasetProfile` | No title, keywords, themes, media types or temporal fields. R3's `abstained(insufficient_input)` path. |
