# Example inputs

The Run tab's **Load example** offers these. Each carries `schema_class`, and the shell lists an
example only for agents that accept that class. They are copies of the workbench's samples, held
here because the app must not depend on the workbench. TODO(#108): agents should declare their own
examples, and this directory should then go.

| File | Class | Purpose |
|---|---|---|
| `soil-chemistry.profile.json` | `DatasetProfile` | The standards advisor's succeeded path, with field-level recommendations. |
| `empty.profile.json` | `DatasetProfile` | No title, keywords, themes, media types or temporal fields. The standards advisor's `abstained(insufficient_input)` path. |
| `orda-record.metadata.json` | `MetadataRecord` | A minimal repository record with no licence. `quality.reviewer`'s succeeded path with one unmet criterion. |
| `hello.salutation.json` | `Salutation` | Whom to greet. `hello.world`'s succeeded path. |
| `director.message.json` | `Message` | A greeting for the orchestrator (`director.stub` or `orchestrator.model`) to delegate to `hello.world`. |
