# Data Director Workbench

The workbench is a test bed for building and testing Data Director sub-agents. It is for the
software engineers and testers who write those agents. It is not the reference implementation
itself.

Each agent states what input it reads, what output it returns, and what that output is based on.
The workbench runs the agent and checks that it kept to those statements. It records every run
so that a person can inspect what the agent did and why. [`docs/architecture.md`](docs/architecture.md)
explains how the pieces fit together.

## Quick start

Requires Python 3.14 and [`uv`](https://docs.astral.sh/uv/). No account or API key is needed.

```sh
uv sync --all-extras
uv run pytest                                          # network blocked; everything offline
uv run workbench agents                                # what is registered, what each accepts
uv run workbench invoke --agent quality.reviewer --input samples/orda-record.metadata.json
uv run workbench invoke --agent fact.checker     --input samples/claim.json
uv run workbench invoke --agent hello.world      --input samples/hello.salutation.json
uv run workbench invoke --agent quality.reviewer --input samples/claim.json   # failed: input-not-accepted
uv run workbench invoke --agent stub.abstain     --input samples/claim.json   # abstained
uv run workbench serve                                 # then open http://127.0.0.1:8000/shell/
```

`invoke` prints the agent's response and the result of the grounding check. It also writes a
folder, `runs/<invocation_id>/`, holding the request, the response, the trace of the run and a
provenance record. To re-run the grounding check on a finished run, use
`workbench lint <spans.jsonl> <envelope.json>`.

## Agents

| Agent | Reads | Grounding mode | Returns | Purpose |
|---|---|---|---|---|
| `hello.world` | `Salutation` | `none` | `Greeting` | The template to copy when writing a new agent. |
| `quality.reviewer` | `MetadataRecord` | `input_only` | `QualityReview` | Scores how complete a metadata record is. A demonstration only. |
| `fact.checker` | `Claim` | `retrieval` | `FactCheck` | Checks a claim against a few packaged sources by word overlap. A demonstration only. |
| `stub.abstain` | any input | `none` | — | Always declines, to test the non-success path. |
| `r3.standards-advisor` | `DatasetProfile` | `retrieval` | `Recommendations` | Recommends standards from FAIRsharing. Not yet ported; see [Limitations](#limitations). |

The grounding mode says what an agent's output may be based on; see
[`docs/grounding.md`](docs/grounding.md). To add an agent, follow
[`src/workbench/agents/README.md`](src/workbench/agents/README.md).

## Further reading

- [Architecture](docs/architecture.md): the components, the order they run in, and where the
  code lives.
- [The conductor](docs/conductor.md): the function that runs an agent and applies every check.
- [The contract](docs/contract.md): the request an agent receives and the response it returns.
- [Grounding](docs/grounding.md): the rules that tie an agent's output to its sources.
- [Glossary](docs/glossary.md): the terms used in this directory.
- [`CONFORMANCE.md`](CONFORMANCE.md): which Blueprint requirements the tests demonstrate. It is
  generated from the test results. A requirement with no passing test is marked
  *unsubstantiated*.
- [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md): the plan for this version.
- [`docs/adr/`](docs/adr/): the design decisions, one record per decision.

## Limitations

- The R3 standards advisor predates the current agent interface. It is registered as
  unavailable and its tests are marked as expected failures until it is ported. TODO — see
  [`src/workbench/agents/r3/factory.py`](src/workbench/agents/r3/factory.py).
- `quality.reviewer` and `fact.checker` are demonstrations. Their scoring rules are simple and
  chosen by hand. They exist to exercise the harness.
- Energy use (P14) has a field in the response but is not measured.
- Validation reports are meant to use the SHACL vocabulary. Only JSON Schema validation runs so
  far.
- Frictionless has no RDF namespace, so `TableField` slots link to it with `see_also` instead of
  a URI.
- The w3id namespace used for problem types and agent identifiers is not yet registered.
- The shell is not tested in a browser in CI.
- Each request produces one response. Conversation, orchestration and streaming are deferred
  (`docs/MVP_PLAN.md` §6).

## Environment

See [`env.example`](env.example). The defaults run entirely offline.
