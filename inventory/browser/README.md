# @data-director/inventory

Reading a `FileInventory`, the document [`dd-inventory`](../README.md) writes, in TypeScript. The
app uses it to show a researcher what an inventory holds; the browser scanner (#554) will join it
here, so that what makes an inventory and what reads one share one set of types.

The package holds no user interface and no policy, and has no runtime dependencies. It is pure
functions over the contract's slots, in British English where it puts facts into words. The
server remains the authority on whether an inventory is valid: it checks the document against
the contract's class schema before a project keeps it ([Projects](../../docs/specs/projects.md)).

| Module | Gives |
| --- | --- |
| `types` | `FileInventory`, `InventoryFile`, `TableField`, `IdentificationMethod`, with the contract's slot names |
| `parse` | `parseInventory(text)`, `asInventory(value)` and `looksLikeInventory(text)`; `NotAnInventory` says in a sentence what is wrong |
| `summary` | `summarise(inventory)`: totals, formats by media type, how formats were identified, ambiguous and unrecognised files, tables, limitations |
| `tree` | `folderTree(files)`: the files as folders, each with its file count and size |
| `search` | `searchFiles(files, query)`: by path, media type, PRONOM identifier or column name |
| `format` | `formatBytes`, `formatFileCount`, `formatDate`, `describeInventory`, `identificationLabel`, `pronomUrl` |
| `making` | `MAKING_AN_INVENTORY`, how to make an inventory on each operating system, and `systemFromPlatform(platform)` |

`making` reads its text from `src/making.json`. The user guide's
[Making an inventory](../../docs/guide/user-guide/making-an-inventory.md) page renders the same file
(`docs/hooks_inventory.py`), so the app's **Make an inventory** dialog and the guide cannot say
different things. Change the wording there, not in either reader.

```ts
import { parseInventory, summarise, formatBytes } from "@data-director/inventory";

const summary = summarise(parseInventory(text));
console.log(`${summary.fileCount} files, ${formatBytes(summary.bytes)}`);
```

It is consumed as TypeScript source, with no build step: `app/web` depends on it with
`"file:../../inventory/browser"`, and Vite compiles it with the app. It is not published.

```console
$ cd inventory/browser
$ npm ci
$ npm run lint && npm run typecheck && npm test
```

The types mirror the contract's `FileInventory` class (`sdk/src/dd_sdk/schema/data_director.yaml`)
by hand. The tests read a copy of the workbench's soil-survey sample, which `dd-inventory` wrote,
so a change to what the command writes shows up here when the copy is refreshed (#555 will share
one sample folder between both scanners).
