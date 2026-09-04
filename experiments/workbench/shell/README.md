# Read-only shell

One HTML page, no build step. It loads React and react-jsonschema-form (RJSF) from a CDN as ES
modules and renders an `Envelope` from the contract's generated JSON Schema
(`/schema/envelope.schema.json`). There are no per-agent templates: a new agent's payload renders
as soon as its class is in the LinkML schema.

Serve it with `uv run workbench serve` and open <http://127.0.0.1:8000/shell/>. The page needs
network access to `esm.sh` for the libraries; everything else is local.

## What it shows

- **Outcome banner** coloured by `outcome.status`, with the statement, reason code and problem.
- **The envelope**, rendered read-only from schema, field by field.
- **Derivation badges.** `uischema.json` declares, per field, how its value came about:
  `verified` (set by the harness or read from a registry), `model` (written by a language model,
  shown as *AI-derived*), `template` / `lexical` / `registry`. Where a field names a
  `dd:derivation_field`, the badge reads the sibling's live value, so a rationale that fell back to
  the template is badged as template even though the slot is normally model-written. This is the
  convention a new agent inherits by declaring which of its fields are model-derived.
- **Evidence drawer**: the FAIRsharing records the trace shows were retrieved, with content hashes.
- **Trace line**: trace id, model, token counts, and the energy slots (null / `not_measured`).

Loads a run by `?invocation_id=` (AG-UI replay from the store), from the stored-runs list, or by
running either agent on the bundled soil-chemistry sample.

## Not here, on purpose

No editing, no feedback capture, no streaming, no `suspended` interrupt. Workshop participants
evaluate a fixed output; they do not change it. Those arrive with the AG-UI events that need them.

The browser is not exercised in CI. `tests/test_shell.py` checks that `uischema.json` covers every
model-derived field the agents can produce and is served by the app.
