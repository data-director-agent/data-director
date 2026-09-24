# Read-only shell

A developer tool: run a registered agent on a sample and inspect the envelope it produced. It is
not an end-user interface; end users will reach the agents through a chat interface or apps built
on them (TODO: not yet designed).

One HTML page, no build step. It loads React and react-jsonschema-form (RJSF) from a CDN as ES
modules and renders an `Envelope` against the contract's generated JSON Schema
(`/schema/envelope.schema.json`). The agent and sample pickers are filled from `GET /agents` (the
registry's manifest, ADR-0010) and `GET /samples`; the shell names no agent. A new agent's payload
renders as soon as its class is in the LinkML schema and the agent ships a uischema fragment.

Serve it with `uv run workbench serve` and open <http://127.0.0.1:8000/shell/>. The page needs
network access to `esm.sh` for the libraries; everything else is local.

## What it shows

The left column holds the controls: an agent picker grouped by id prefix, with a card describing
the chosen agent (description, grounding mode, accepted input classes, requirement ids;
unavailable agents are listed in their own group, with their reason), a sample picker filtered to the classes the agent accepts, **Run** (`Ctrl`+`Enter`), and
the stored runs. The right column shows one run:

- **Summary**: `outcome.status`, `reason_code`, `agent_id@agent_version`, `grounding_mode`,
  `completed_at`, `invocation_id` (copyable) and the statement; Problem Details when present.
- **Input | Payload** side by side. The input is known only for runs started from the same browser
  tab; the envelope stores the input's hash, not the input, so a replay shows the hash instead.
- **Payload**, rendered by RJSF from the payload class in the envelope schema's `$defs` and the
  agent's fragment (`AgentSpec.uischema`). Custom templates present it as a document rather than a
  disabled form: label/value pairs, and an array of objects as rows under a header.
- **Derivation badges.** A fragment declares, per field, how its value came about: `verified`
  (set by the harness or read from a registry; the unbadged default), `model` (written by a
  language model), `template` / `lexical` / `registry`. Where a field names a
  `dd:derivation_field`, the badge reads the sibling's live value, so a rationale that fell back to
  the template is badged as template even though the slot is normally model-written. This is the
  convention a new agent inherits by declaring which of its fields are model-derived.
- **Evidence** as a table: source, retrieval time, canonicalisation, snapshot and content hash,
  with a *cited* marker where the hash appears in the payload's `grounded_on`. The marker is a
  visual cross-check; the grounding linter is what enforces it.
- **Telemetry**: trace id, model, token counts, and the energy slots (null / `not_measured`).
- **Envelope JSON** and **Input JSON** tabs, with copy and download.
- **Built-in help.** A `?` button beside each contract term (envelope, outcome status,
  `grounding_mode`, `canonicalisation`, `snapshot_ref`, the derivation badges, …) opens a short
  explanation: hover to read it, click to keep it open, `Esc` to close. The **Glossary** button in
  the header lists every term. The text lives in one `GLOSSARY` object in `index.html`, written
  from the definitions in `schema/data_director.yaml`; keep the two in step. A payload field's `?`
  shows the field's own schema description, so an agent documents its payload by describing its
  LinkML slots.

Loads a run by `?invocation_id=` (AG-UI replay from the store), from the stored-runs list, or by
running a chosen agent on a chosen sample.

The envelope-level `uischema.json` is kept as the reference description of the envelope and is
still served at `/schema/uischema.json`, but the page no longer renders the envelope through RJSF:
the summary, evidence and telemetry are laid out directly. TODO: decide whether to drop it.

## Not here, on purpose

No editing, no feedback capture, no streaming, no `suspended` interrupt. Those arrive with the AG-UI events that need them.

The browser is not exercised in CI. `tests/test_shell.py` checks that every agent's fragment badges
its model-writable fields by their derivation sibling, that the base covers the envelope only,
that the glossary explains every outcome status, grounding mode and derivation value, and that the
page names no agent or sample.
