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
| `types` | `FileInventory`, `InventoryFile`, `InventoryPart`, `TableField`, `IdentificationMethod`, `FileRole`, with the contract's slot names |
| `parse` | `parseInventory(text)`, `asInventory(value)` and `looksLikeInventory(text)`; `NotAnInventory` says in a sentence what is wrong |
| `summary` | `summarise(inventory)`: totals, formats by media type, how formats were identified, ambiguous and unrecognised files, tables, limitations |
| `tree` | `folderTree(files)`: the files as folders, each with its file count and size |
| `omit` | `omit(inventory, omission)`: the inventory without the files, folders and columns a researcher left out, with one limitation that counts them and names none; `countOmitted`, `describeOmitted`, `isOmitted` |
| `edit` | The edit model: an `InventoryEdits` value says what a researcher left out and what they stated (a file's description, role and, where the command could not tell, format; a column's description). `edit(base, edits, action)` makes the next value and keeps only real changes, `applyEdits(base, edits)` writes them in (omitting with `omit`), `countEdits` and `describeEdits` say how much changed, `diffInventories` compares two scans, and `carryOver(previous, rescan)` states again on a new scan what was said before, by path. What the command observed is never edited |
| `parts` | An inventory of several folders: `asParts(inventory, folder)` names the folder an inventory of one folder already has, `withPart(stored, scan, folder)` updates that folder's part with a new scan, or adds a folder, and keeps the other parts as they were; `partsOf`, `partOf`, `partProblems` and `partFolderProblem`. A part is replaced whole, never merged file by file. `omit` keeps what was left out counted with its part |
| `search` | `searchFiles(files, query)`: by path, media type, PRONOM identifier or column name |
| `format` | `formatBytes`, `formatFileCount`, `formatDate`, `describeInventory`, `identificationLabel`, `pronomUrl` |
| `hints` | `fileHints(inventory)`: the files whose folder, file or field names, size or digest call for a person to look before deposit (free text, coordinates, someone else's material, terms, system files, empty files, copies), each with what to check; `HINT_LABELS`, `HINT_RULES`, and `HINT_LIMITATION`, the sentence that says no hint is not clearance. A prompt, never a finding: the inventory holds no contents (#449). The rules are a copy of the File Archivist's `hints.yaml`; change both together |
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
