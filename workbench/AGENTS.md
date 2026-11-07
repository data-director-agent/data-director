# workbench

Rules for working on the workbench itself. The repository-wide rules, including the commands for
running tests and checks, are in the root [`AGENTS.md`](../AGENTS.md); the harness's are in
[`../harness/AGENTS.md`](../harness/AGENTS.md) and the agents' in
[`../agents/AGENTS.md`](../agents/AGENTS.md).

## What belongs here

The workbench is a development client of the harness for the people who build and test agents:
the `workbench` CLI, the AG-UI transport, the admin sign-in gate for a deployed workbench, the
viewer (`viewer/`) and its browser tests, and the development configuration it supplies to the
harness (`workbench.config`, `profiles/`, `agents.yaml`, `sources.yaml`).

Nothing else belongs here. In particular, do not add:

- governance code (the conductor, policy gate, input check, linter, source check, stores),
  shared test doubles or anything a second way in would need: put it in `../harness/`;
- anything agents and the harness share (the contract, evidence, span helpers, the agent
  server): put it in `../sdk/`;
- an agent's code, cases, data or scripts: put it in `../agents/<name>/`;
- tests of the repository's scripts or its shipped configuration as a whole: put them in
  `../scripts/tests/`;
- anything the app needs: the app must not depend on the workbench.

If what you are writing would be useful to the app, an agent or another way in to the harness,
it does not belong in the workbench.

## Load-bearing things

- **`src/` imports no agent.** Agents are services reached through `RemoteAgent`
  (`dd_harness.remote`); `agents.yaml` lists their URLs. Tests may import agent packages to serve
  them in memory, and `src/workbench/` must not.
- **The workbench knows a class only from a card.** If you find yourself adding a list of class
  names, or an agent's name, to the CLI, transport or viewer, stop.
- **`viewer/icons.svg` is generated.** It is a sprite of Lucide icons (ISC,
  `viewer/icons.LICENCE`) built by `scripts/build_icons.py` from a pinned, hash-checked
  `lucide-static`; add an icon to `ICONS` there and rerun, never by hand. Icons are decorative
  (`aria-hidden`), sit beside visible text or inside a labelled control, and each outcome status
  has exactly one (`STATUS_ICONS`).
- **The viewer's CDN modules are pinned and recorded.** Each `esm.sh` import in `viewer/js/`
  names an exact version, and `browser_tests/esm.sh.har.zip` holds their responses so the browser
  tests run without the network. Re-record it with `--update-har`, never by hand;
  `test_viewer.py` fails if an import is missing from it. A browser test fails on any console
  error; a test that expects one removes it from `page_errors`.

```bash
uv run pytest workbench/browser_tests           # the viewer in Chromium; `playwright install chromium` once
```
