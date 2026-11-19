# @data-director/agent-view

Inspecting what a Data Director agent publishes, in TypeScript and React: its A2A agent card,
the Data Director extensions on it, and the payloads it returns. It is one library for every
front end, so that the app, the workbench and anything after them show an agent the same way.

It names no agent class. Everything it shows comes from the card, the class's JSON Schema
that the card carries, and whatever the host registers.

| Entry point | Gives |
| --- | --- |
| `@data-director/agent-view` | Headless, with no runtime dependencies. `readCard(json)` reads a card that arrived as JSON and never throws; it lists what it could not read in `issues`. `agentSpecOf(card)` reads the `agent-spec/v0` extension (`describe(spec)` in `dd_sdk.agent`) and `manifestOf(card)` reads the harness's `manifest/v0`. `readAgentSpec` and `specFromRaw` turn a raw specification into an `AgentSpec`. `shapeOf`, `resolve` and `properties` read a class's JSON Schema. Also: the envelope's types, `evidenceKey`, `documentOf` and wording (`fieldName`, `className`, `DERIVATION`). |
| `@data-director/agent-view/react` | `AgentCardView` is the whole card. `AgentSpecView` is one agent's specification, field by field, with each schema unfoldable. `ManifestView` lists a harness's agents. `ExtensionView` draws one extension. `PayloadView` lays out a payload from its schema, with derivation badges, `grounded_on` links to the evidence, and a drafted document shown as a document. `AgentViewProvider` takes the host's slots and registries. |
| `@data-director/agent-view/styles.css` | Styles in the `components` cascade layer. Each colour and length is a custom property that falls back to the app's tokens (`--space-1`, `--color-border`, and so on), so a host themes the components by setting those. |

```tsx
import { AgentCardView, AgentViewProvider, PayloadView } from "@data-director/agent-view/react";
import { agentSpecOf, readCard } from "@data-director/agent-view";
import "@data-director/agent-view/styles.css";

const card = await (await fetch(`${agentUrl}/.well-known/agent-card.json`)).json();
<AgentCardView card={card} />;

const spec = agentSpecOf(readCard(card).card!)!;
<AgentViewProvider components={{ Markdown }} renderers={{ SomeClass: SomeClassView }}>
  <PayloadView
    payload={envelope.payload}
    schema={spec.payload ? spec.schemas[spec.payload] : undefined}
    className={spec.payload}
    derivations={spec.derivations}
    evidence={envelope.evidence ?? []}
    idPrefix="run-1"
  />
</AgentViewProvider>;
```

## What a host lends

- **`components.Markdown`.** Renders Markdown text. The default shows the text as written.
- **`components.Document`.** Shows a drafted document (`document_text` with its `media_type`).
  The default is the document's title followed by its text. The app swaps in its own view, which
  adds copy and download.
- **`renderers[ClassName]`.** Draws one payload class in place of the schema-driven layout. The
  host registers it; the library ships none, because it names no class.
- **`extensions[uri]`.** Draws one A2A extension's params. The Data Director's own extensions are
  built in. Any other extension is shown as key–value pairs.

## Working on it

It is consumed as TypeScript source, with no build step. `app/web` depends on it with
`"file:../../sdk/browser"`, and Vite compiles it with the app. Its `resolve.dedupe` keeps one
copy of React. The package is not published.

The workbench viewer has no build step, so it cannot import the source yet; moving it over is
TODO(#677).

The agent card in `tests/fixtures/` is the one the SDK actually serves. It is built from the
SDK's test specification by `sdk/tests/test_agent_view_fixtures.py`, so run that test after
changing how cards are built: locally it rewrites the fixture, and in CI it fails if the fixture
is stale. The harness's card is made from the same card in `tests/fixtures.ts`.

```console
$ cd sdk/browser
$ npm ci
$ npm run lint && npm run typecheck && npm test
```

The lockfile was written with npm 11: npm 10's `npm install` fails on the package's
`overrides`. `npm ci` works on either version.
