# example.hello

**Template, alpha** (`0.1.1a1`): the Friendly Greeter, the smallest agent that meets the whole of
the contract. It greets whoever the input names, in English, Welsh, French or German, and does
nothing else. Copy it to start a new agent ([Agents](../README.md)).

| Part | In this agent |
|---|---|
| Input | `Salutation`: `greeted_name`, and an optional `language` (BCP 47 tag, English if absent). |
| Payload | `Greeting`: `greeting_text`, how it came about (`greeting_derivation`, always `template`) and `grounded_on`. |
| Grounding mode | `none`: deterministic, no retrieval and no model. It cites the input and nothing else. |
| Outcomes | `succeeded` with a greeting; `abstained` (`capability-not-implemented`) for a language it has no greeting for. |
| Steps served | None. A template is not offered to researchers; a real agent names its process-flow steps in `serves`. |

## Run it

```sh
uv run dd-example-hello serve --port 8101
uv run workbench invoke --agent example.hello --input workbench/samples/hello.salutation.json
uv run pytest agents/example-hello
```

## Where to read

`src/dd_agent_example_hello/agent.py` is commented against the numbered recipe in
[`agents/README.md`](../README.md). The classes are declared in
`src/dd_agent_example_hello/schema/hello.yaml`; after editing it, run
`uv run dd-gen-schema agents/example-hello/src/dd_agent_example_hello/schema/hello.yaml`.
