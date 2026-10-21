# Data Director app (alpha)

**Alpha** (`0.1.0a1`). This is the simplest possible Data Director: a chat page in a local
browser, and one language model that can ask R3 (`r3.standards-advisor`) for standards through
the harness. It is exploratory, and its shape will change.

It is built from off-the-shelf parts:

- [Gradio](https://www.gradio.app/) `ChatInterface` provides the page;
- [pydantic-ai](https://ai.pydantic.dev/) runs the agent loop, the tool calls and model
  selection;
- the harness (`harness/`, `dd_harness`) runs R3 through its conductor;
- R3 recommends standards from the committed FAIRsharing snapshot
  (`agents/r3/data/fairsharing/snapshot.jsonl`, CC BY-SA 4.0).

## Run it

From the repository root:

```bash
export ANTHROPIC_API_KEY=...        # or copy app/env.example to app/.env and add --env-file app/.env
export DD_PRINCIPAL_ID=https://orcid.org/...  DD_PRINCIPAL_NAME="..."   # whom runs act for
uv run data-director                # opens http://127.0.0.1:7860
```

`DD_CHAT_MODEL` takes any [pydantic-ai model
string](https://ai.pydantic.dev/models/overview/). The default is `anthropic:claude-sonnet-5`.
To use a local model through Ollama:

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1 DD_CHAT_MODEL=ollama:llama3.1 uv run data-director
```

`DD_CHAT_MODEL=test` selects pydantic-ai's offline test model. It calls every tool and returns
nonsense, which is enough to check the page works without a key. Gradio's `GRADIO_SERVER_PORT`
and `GRADIO_SERVER_NAME` change the address.

## Configuration

The app supplies its own configuration to the harness (ADR-0022). Its reference set is in
`config/`:

| File | What it is | Override |
|---|---|---|
| `config/profile.yaml` | The institutional profile. It enables R3 only. | `DD_PROFILE` |
| `config/agents.yaml` | Agents reached over A2A. Empty: R3 runs in the app's process. | `DD_AGENTS_CONFIG` |
| `config/sources.yaml` | The pinned FAIRsharing snapshot the source check uses. | `DD_SOURCES_CONFIG` |
| `runs/` (not committed) | Where each run is stored. | `DD_RUNS_DIR` |

`DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` are required. Until there is authentication (#17),
every run acts for this operator, not for the person using the page (ADR-0018). The app stops
at start-up, with one line, if either is unset or a file is missing or malformed. R3 reads its
own `DD_R3_*` variables (`agents/r3`).

## What it does

The model is told the Data Director's scope (Blueprint §2.4). It has one tool:

- `recommend_standards(title?, description?, keywords?, themes?, media_types?, fields?)` builds a
  `DatasetProfile` and calls R3 through `Conductor.invoke`. The model is given the outcome, the
  run's `invocation_id`, and each recommendation with the FAIRsharing record it is grounded on.

Each R3 run passes the policy gate, the input check, the grounding linter and the source check,
and is stored in `runs/` with its trace and a Process Run Crate. The workbench viewer
(`uv run workbench serve`) shows it when `DD_RUNS_DIR` names the same directory. The page shows each tool call as a collapsible
note above the answer, with the run it recorded.

The model is told to cite a FAIRsharing record only if the tool returned it, and to say so when
it falls back on general knowledge.

## What it does not do

- The app's own model turn and its final answer are not governed. Nothing checks that the
  answer cites only what R3 returned. TODO: make the app a front end to an orchestrator under
  `delegation` grounding (ADR-0012, #21).
- R3 takes a structured profile, so the model cannot search the snapshot by free text, filter
  by record type or fetch a record by its identifier. R3 recommends vocabularies, ontologies and
  formats, not reporting guidelines.
- The snapshot holds 169 standards records and no repositories or policies. Conversation
  history lives in the browser page only, and is lost on reload.

This package substantiates no Blueprint requirement, and its tests carry no requirement marker.
