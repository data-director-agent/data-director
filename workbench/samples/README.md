# Sample inputs

Every sample carries `schema_class`, which names its input class; the shell lists a sample only
for agents that accept that class, and `workbench invoke` reads it to parse the document.

| File | Class | Purpose |
|---|---|---|
| `orda-record.metadata.json` | `MetadataRecord` | A minimal repository record, hand-derived from the soil-chemistry dataset, with no licence. Exercises `quality.reviewer`'s succeeded path with one unmet criterion. |
| `hello.salutation.json` | `Salutation` | Whom to greet. Exercises `hello.world`, the template agent, on its succeeded path. |
| `director.message.json` | `Message` | A greeting addressed to the orchestrator. Exercises `director.stub`'s delegation to `hello.world`; needs `workbench serve`, since `invoke` issues no delegation grant. |
| `claim.json` | `Claim` | A statement about DOIs that the packaged sources support. Exercises `fact.checker`'s succeeded path. |
| `soil-chemistry.profile.json` | `DatasetProfile` | Hand-derived from `experiments/standards-advisor/samples/soil-chemistry.metadata.json` and that CSV's header. R3's succeeded path, including field-level (ISO 8601) recommendations, once R3 is ported. |
| `empty.profile.json` | `DatasetProfile` | No title, keywords, themes, media types or temporal fields. R3's `abstained(insufficient_input)` path. |

```sh
uv run workbench agents
uv run workbench invoke --agent quality.reviewer --input samples/orda-record.metadata.json
uv run workbench invoke --agent fact.checker    --input samples/claim.json
uv run workbench invoke --agent hello.world     --input samples/hello.salutation.json
uv run workbench invoke --agent quality.reviewer --input samples/claim.json   # failed: input-not-accepted
```
