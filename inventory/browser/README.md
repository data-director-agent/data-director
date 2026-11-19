# @data-director/inventory

Reading a `FileInventory`, the document [`dd-inventory`](../README.md) writes, in TypeScript. The
app uses it to show a researcher what an inventory holds. It also builds the
[browser bundle](#browser-bundle) of `dd-inventory` itself, and holds the
[browser scanner](#browser-scanner) that runs it over a folder the researcher chooses, so that
what makes an inventory and what reads one live together.

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
| `hints` | `fileHints(inventory)`: the files whose folder, file or field names, size or digest call for a person to look before deposit (free text, coordinates, someone else's material, terms, system files, empty files, copies), each with what to check; `HINT_LABELS`, `HINT_RULES`, and `HINT_LIMITATION`, the sentence that says no hint is not clearance. A prompt, never a finding: the inventory holds no contents (#449). The rules are a copy of `dd_sdk.inventory_hints` (`sdk/`), which the File Archivist and the harness's deposit check read; change both together |
| `making` | `MAKING_AN_INVENTORY`, how to make an inventory on each operating system, and `systemFromPlatform(platform)` |
| `scanner/` | The [browser scanner](#browser-scanner): `fromDirectoryHandle`, `fromFileList` and `fromEntries` turn a chosen folder into a `ChosenFolder`; `fetchBundle` fetches the bundle for the worker; `startScan` runs a scan in the worker (`scanner/worker.ts`) and gives its events and outcome |

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

## Browser bundle

The browser scanner is `dd-inventory` itself, run under [Pyodide](https://pyodide.org/) in a Web
Worker: one scanner in two runtimes ([spike on #367](https://github.com/data-director-agent/data-director/issues/367#issuecomment-6708613929)).
`bundle/` builds what that needs into one folder the app can serve from its own origin, and checks
that it writes the command's inventory. It is development tooling: nothing under `src/` imports
it, and Pyodide is a development dependency of this package only.

```console
$ cd inventory/browser
$ npm ci
$ npm run bundle      # writes dist/inventory-bundle/; needs uv, and the network on the first run
$ npm run parity      # the command natively and under Pyodide, on ../tests/data/mixed
$ node bundle/parity.ts ../tests/data/disclosure/direct   # or on another folder
```

`dist/inventory-bundle/` holds:

- Pyodide's runtime (`pyodide.mjs`, `pyodide.asm.mjs`, `pyodide.asm.wasm`, `python_stdlib.zip`),
  copied from the `pyodide` npm package, pinned exactly in `package.json`;
- `wheels/`: the command's wheel, built by `uv build` from this commit, and every wheel it needs;
- `pyodide-lock.json`: a lock of those wheels alone, each with its SHA-256, which Pyodide checks
  as it installs them. The command's entry depends on every other wheel, so
  `pyodide.loadPackage("data-director-inventory")` installs the bundle (`src/scanner/runtime.ts`) and
  nothing is fetched from PyPI or a CDN;
- `manifest.json`: the Pyodide and command versions, each wheel with its source and digest, and
  each file's size, raw and gzipped;
- `NOTICES.md` (`bundle/notices.ts`): the licence of Pyodide and of every wheel, with where its
  source is, and the Open Government Licence attribution for the PRONOM signatures fido carries.
  Each wheel's licence is read from its own metadata, and a wheel naming none fails the build.
  Serving the bundle redistributes all of it, so the notices go with it; no scan reads them, so
  they are not in the manifest's `files`.

Deployments build it from the commit they run: the release image in a stage of its own
(`docker/release.Dockerfile`), and the VM deploy beside the app's shell (`deploy/deploy.sh`), each
copying it to `app/web/dist/inventory-bundle/`, where the app serves it.

Which wheel is taken (`bundle/resolve.ts`): the command's dependencies are those `uv export`
gives from the workspace lock, leaving out any whose environment marker does not hold under
Pyodide. A package Pyodide builds is taken from Pyodide's lock, with what Pyodide's lock says it
depends on, since Pyodide built and tested those versions together; it compiles some of them
(`pydantic-core`, PyYAML, MarkupSafe, rpds-py), and its `pydantic` matches its `pydantic-core`
where the workspace's newer one would not. Any other package is the workspace lock's pure Python
wheel, and a package with neither fails the build. Each download is checked against the SHA-256
in its lock (Pyodide's comes with the npm package) and kept in `.cache/wheels/`, so a rebuild
needs no network.

The personal-data detector, Presidio with pattern recognisers only
([Personal data](../../docs/specs/personal-data.md)), declares spaCy, preshed and numpy and imports
only spaCy, which does not build for Pyodide. The export leaves the three out with what only they
need (`--prune`), and `bundle/spacy-stub/` takes spaCy's place: the names Presidio's modules import
from spaCy and thinc, and nothing that processes language. `bundle/write_wheel.py` makes it a
wheel, the same bytes each time, which the command's entry in the lock depends on.
`inventory/tests/test_spacy_stub.py` runs the command with the stub in spaCy's place and checks
that it makes the same inventory, so a Presidio release that imports more of spaCy fails there
first. The detector adds about 3.5 MB gzipped to the bundle.

The parity check (`bundle/parity.ts`) runs `dd-inventory` natively through `uv`, then loads the
bundle in Node, mounts the folder at `/data` and runs `make_inventory` there. It fails on any
difference but `inventory_made_at` and the runtime's label in `inventory_tool_version`
(`0.1.0a4` natively, `0.1.0a4+pyodide.314.0.8` under Pyodide), and on any network request under
Pyodide. `inventory/tests/data/mixed` is the shared sample folder: CSV and TSV tables of every
simple field type, a format identified by its byte signature, a container format, a PNG named
`.csv`, an empty file, a nested folder, and hidden files. CI's **Inventory browser bundle
(parity)** job runs both scripts whenever the command, its dependencies, the bundle or the sample
change, and writes the bundle's size and its Pyodide, fido and PRONOM signature versions to the
job summary, so that a change to any of them is seen.

The bundle carries Pyodide (MPL-2.0), fido (Apache-2.0), The National Archives' PRONOM
signatures (Open Government Licence) and some 40 other wheels, each credited in `NOTICES.md`,
which the app links to beside **Describe a folder…**.

## Browser scanner

`src/scanner/` runs the bundle in a Web Worker over a folder the researcher chooses, so that a
researcher with only a browser can make an inventory (#554). The files are read where they are;
only the inventory comes back to the page.

1. **Choosing a folder.** `fromDirectoryHandle` takes a folder from `showDirectoryPicker`
   (`canPickDirectory()` says whether the browser has it), `fromFileList` the files of an
   `<input type="file" webkitdirectory>`, and `fromEntries` a dropped folder's
   `webkitGetAsEntry()`. Each gives a `ChosenFolder`: the folder's name and every file under it,
   by its path relative to the folder. Hidden files are kept; the command skips and counts them
   itself. WebKit's `webkitdirectory` offers none to the page, though (below). Prefer the directory picker where there is one: Chromium's prompt for
   `webkitdirectory` asks whether to *upload* the files, which is not what happens.
2. **The bundle.** The page fetches the whole bundle with `fetchBundle(baseUrl)` and hands it to
   the worker, which has no network: it imports Pyodide's two scripts from `blob:` URLs made of
   those bytes, and answers Pyodide's requests for the rest from memory (`serveFrom`), checking
   each wheel against the SHA-256 in the bundle's lock as a browser would. Caching the bundle
   across scans is left to HTTP caching where the app serves it.
3. **The scan.** `startScan(worker, assets, folder, onEvent)` posts the request to a fresh worker.
   The package exports the worker's module as `@data-director/inventory/scanner/worker`, which a
   Vite app starts with `import ScanWorker from "@data-director/inventory/scanner/worker?worker"`
   and `new ScanWorker()`, as `app/web/src/scan/scanner.ts` does. The app offers it both where
   an inventory is first made and where the project's inventory is updated with a new scan. The
   worker mounts the files read-only at `/data` with Emscripten's WORKERFS, which reads slices of
   each file on demand and copies none of them, and runs the command's `make_inventory` there.
   `onEvent` hears each stage (`starting`, `installing`, `reading`) and each file
   (`progress`: path, size, done, total). The outcome is the inventory's JSON text, a sentence
   saying why there is none, or `cancelled`: `cancel()` ends the worker. A worker serves one scan.

The worker is meant to run under this Content Security Policy, which whoever serves it sends with
the worker's script:

```text
default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'
```

`'unsafe-eval'` is not needed, and neither is `'self'` in `script-src`. The app sends it with its
built worker, `assets/inventory-scanner-<hash>.js` (`dd_app.worker_policy`, and its preview
server), and serves the bundle at `/inventory-bundle/` where it has been built.

`npm run e2e` (after `npm run bundle`) proves this in Chromium, Firefox and WebKit.
`e2e/vite.config.ts` builds a test page and serves it with the bundle from one origin, sending the
worker the policy above. The test copies `../tests/data/mixed`, adds a file holding a canary
string, chooses the copy through `webkitdirectory`, and checks that the inventory equals the
command's on the same copy (apart from when it was made and the runtime's label, and in WebKit the
hidden-file sentence), that progress reached the last file, and that every request was a `GET` of
the page or the bundle with no body and no canary. CI's **Inventory
browser bundle (parity)** job runs it after the parity check.

What differs from the command on disk:

- **Symbolic links.** Browsers do not show them: a linked file is offered as a file, and so is
  described where the command would skip it and say so.
- **Speed and memory.** About three times slower than the command, and ten times on hashing (see
  the [spike on #367](https://github.com/data-director-agent/data-director/issues/367#issuecomment-6708613929)).
  Memory rises while a large file is hashed, almost all of it in the renderer that runs the
  worker. In headless Chromium on a 16 GB machine the whole browser rose from about 0.4 GB to
  2.4 GB on an 8 GB file and to 2.8 GB on a 16 GB file. A 50 GB file was hashed correctly in
  9.4 minutes (about 91 MB/s), with the browser peaking 2.7 GB above where it started, so the
  growth levels off rather than following the file's size.

  The memory is what WORKERFS's reads leave for the garbage collector: each read is a `Blob`
  slice and an `ArrayBuffer` from `FileReaderSync`, and the same loop in a bare worker, with no
  Pyodide, grows alike. Chromium collects them only as V8 sees memory pressure, which it judges
  by the machine's memory, not by what the system will actually let it have. Detaching each
  buffer once it is copied (`ArrayBuffer.prototype.transfer(0)`) made it worse: the browser
  then grew by the whole file, as V8 no longer counted the memory and so never collected. With
  the browser held to 1 GB by a cgroup (a scan of a small folder needs about 0.5 GB), a 4 GB file
  had the renderer killed, which closes the page and the app with it, not only the scan. So
  **Describe a folder…** advises the command before describing a folder with a file of 4 GB or
  more, and describes it only if the researcher goes on
  (`app/web/src/components/inventory/LargeFileNotice.tsx`).
- **Browsers.** CI runs the scanner, and the app's **Describe a folder…** from choosing to
  attaching, in Playwright's Chromium, Firefox and WebKit (the engine of Safari). Firefox and
  WebKit have no `showDirectoryPicker`, so they always take a folder through `webkitdirectory` or
  a drop. WebKit's `webkitdirectory` offers no hidden file or folder, so the command never sees
  them and its inventory leaves out the sentence saying they were skipped; the files it describes
  are the same. The app's accessibility check of the dialog runs in Chromium and WebKit only: in
  Playwright's Firefox, axe crashes the page after a `getByRole("region")` query, with or without
  a scan.
