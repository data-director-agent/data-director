# chat — an alpha Data Director

**Alpha** (`0.1.0a1`). This is the simplest possible Data Director: a chat page in a local
browser, and one language model that can search a FAIRsharing snapshot. It is exploratory, and
its shape will change.

It is built from off-the-shelf parts:

- [Gradio](https://www.gradio.app/) `ChatInterface` provides the page;
- [pydantic-ai](https://ai.pydantic.dev/) runs the agent loop, the tool calls and model
  selection;
- R3's `SnapshotBackend` searches the committed FAIRsharing snapshot
  (`../r3/data/fairsharing/snapshot.jsonl`, CC BY-SA 4.0).

## Run it

From the repository root:

```bash
export ANTHROPIC_API_KEY=...        # or put it in workbench/.env and add --env-file workbench/.env
uv run dd-chat                      # opens http://127.0.0.1:7860
```

`DD_CHAT_MODEL` takes any [pydantic-ai model
string](https://ai.pydantic.dev/models/overview/). The default is `anthropic:claude-sonnet-5`.
To use a local model through Ollama:

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1 DD_CHAT_MODEL=ollama:llama3.1 uv run dd-chat
```

`DD_CHAT_MODEL=test` selects pydantic-ai's offline test model. It calls every tool and returns
nonsense, which is enough to check the page works without a key. Gradio's `GRADIO_SERVER_PORT`
and `GRADIO_SERVER_NAME` change the address.

## What it does

The model is told the Data Director's scope (Blueprint §2.4). It has two tools:

- `search_fairsharing(query, record_type?, limit?)`: a BM25 search over the snapshot;
- `get_fairsharing_record(fairsharing_id)`: one record in full.

The model is told to cite a FAIRsharing record only if a tool returned it, and to say so when it
falls back on general knowledge. The page shows each tool call as a collapsible note above the
answer.

## What it does not do

It is not an A2A service. The workbench never calls it, so none of the contract applies:

- there is no policy gate, input check, grounding linter or evidence hashing;
- no run is recorded;
- nothing checks the model's citations.

The snapshot holds 169 standards records and no repositories or policies. Conversation history
lives in the browser page only, and is lost on reload.

This package substantiates no Blueprint requirement, and its tests carry no requirement marker.

TODO: decide whether this becomes a model-backed replacement for `director.stub` (delegation
mode, through the workbench's Chat page) or stays a standalone prototype.
