# Read-only shell

One HTML page, no build step. It loads React and react-jsonschema-form (RJSF) from a CDN as ES
modules and renders an `Envelope` from the contract's generated JSON Schema
(`/schema/envelope.schema.json`). The agent and sample pickers are filled from `GET /agents` (the
registry's manifest, ADR-0010) and `GET /samples`; the shell names no agent. A new agent's payload
renders as soon as its class is in the LinkML schema and the agent ships a uischema fragment.

Serve it with `uv run workbench serve` and open <http://127.0.0.1:8000/shell/>. The page needs
network access to `esm.sh` for the libraries; everything else is local.

## What it shows

- **Outcome banner** coloured by `outcome.status`, with the statement, grounding mode, reason
  code and problem.
- **The envelope**, rendered read-only from schema, field by field.
- **Derivation badges.** The base `uischema.json` covers the envelope; each agent ships a fragment
  for its payload (`AgentSpec.uischema`), and the shell composes the two per render. A fragment
  declares, per field, how its value came about:
  `verified` (set by the harness or read from a registry), `model` (written by a language model,
  shown as *AI-derived*), `template` / `lexical` / `registry`. Where a field names a
  `dd:derivation_field`, the badge reads the sibling's live value, so a rationale that fell back to
  the template is badged as template even though the slot is normally model-written. This is the
  convention a new agent inherits by declaring which of its fields are model-derived.
- **Evidence drawer**: the source records the trace shows were retrieved (or, for an
  input-grounded agent, the input itself), with content hashes.
- **Trace line**: trace id, model, token counts, and the energy slots (null / `not_measured`).

Loads a run by `?invocation_id=` (AG-UI replay from the store), from the stored-runs list, or by
running a chosen agent on a chosen sample; samples are filtered to the input classes the agent
accepts.

## Not here, on purpose

No editing, no feedback capture, no streaming, no `suspended` interrupt. Workshop participants
evaluate a fixed output; they do not change it. Those arrive with the AG-UI events that need them.

The browser is not exercised in CI. `tests/test_shell.py` checks that every agent's fragment badges
its model-writable fields by their derivation sibling, that the base covers the envelope only,
and that the page names no agent or sample.
