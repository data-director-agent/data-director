# Architecture review

A review of where complexity is building up in the repository and what to do about it, written in
November 2026 against `main` at `dc4a0e6`. It names the code that is growing in an uncontrolled
way, proposes refactors in order of value, and describes the automatic checks added alongside it
so that new code cannot add to the problem while the refactors wait.

Figures (line counts, branch counts, method counts) are from that commit and will drift; the
`file:line` references are to it.

## Summary

The boundaries *between* packages are in good shape and well defended. The debt is *inside*
packages: a handful of functions, classes and components have become the place where every new
feature goes, and some code has been copied between agents because there was nowhere shared to put
it. Nothing measured either until this review.

| Concern | Where | Size |
|---|---|---|
| A god function | `app/src/dd_app/app.py:213` `build_app` | 1,374 lines, about 270 branch points, about 50 route handlers as closures |
| A god class | `harness/src/dd_harness/projects.py:360` `Projects` | about 1,000 lines, about 75 methods, about nine subdomains |
| A long pipeline method | `harness/src/dd_harness/conductor.py:495` `Conductor._run` | 454 lines |
| A long agent `run` | `agents/advisor-policy/src/dd_agent_advisor_policy/agent.py:291` | 432 lines, about 140 branch points |
| A god component | `app/web/src/components/conversation/ConversationHome.tsx` | 890 lines, 22 `useState`, 8 `useEffect`, 5 hand-written loaders |
| Copying between agents | the agent skeleton, registry clients, explainers | about 400 lines |
| Lists kept by hand | the 15 agents in `pyproject.toml` and deployment files | 14 lists in `pyproject.toml` alone; 7 agents had fallen out of one |

## What already works

These mechanisms are sound and should be kept. The new checks copy their patterns.

- **Package direction** is enforced by Import Linter contracts in the root `pyproject.toml`
  (layers, forbidden imports, agent independence) and by `scripts/check_boundaries.py`, whose
  exceptions in `scripts/boundaries.toml` can only shrink, because a stale one fails.
- **Declared dependencies** are checked per member by deptry (`scripts/check_dependencies.py`).
- **Canaries** plant a violation of each kind and expect the check to fail
  (`scripts/tests/test_architecture_canary.py`, `app/web/src/architecture.test.ts`), so a
  misconfigured check cannot pass silently.
- **Types** are strict on both sides: mypy `strict` and TypeScript with
  `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`.
- **Storage** has one conformance kit (`harness/src/dd_harness/testing/storage.py`) run against both
  the file backend (`harness/tests/test_storage.py`) and PostgreSQL
  (`harness/tests/test_postgres.py`), so the backends cannot quietly drift.
- **The wire between front end and server** is pinned by golden fixtures that the Python tests
  rewrite (`app/tests/support.py` `check_fixture`) and AG-UI cassettes.
- **The front end's layers** are checked by eslint-plugin-boundaries and dependency-cruiser.
- **Model calls are centralised**: no agent imports a provider's SDK; every call goes through
  `dd_sdk.model.call`.

## Findings

### 1. `build_app` holds the whole app

`app/src/dd_app/app.py:213` is one function of 1,374 lines. Inside it are:

- authentication middleware as closures;
- about 50 route handlers as nested closures, from line 320 to 1403;
- a route table of 46 entries.

Consequences:

- **No handler can be imported or unit-tested on its own.** Every test goes through the whole app.
- **Requests are validated by hand.** There are 14 `await request.json()` calls and 56 `_refused(`
  calls. `send_turn` (line 389) alone has about 12 refusal paths, where `reply_answers` already
  shows the better pattern of a Pydantic request model.
- **Domain rules sit in handlers.** `delete_project` (526–564) checks that the typed title matches
  the project, and `choose_repository` (963–1007) wires the registry itself.
- **Handlers reach past `Governance` to the store.** There are 26 uses of `governance.projects` and
  32 direct `store` calls. That makes `Governance` a facade with holes in it.

### 2. `Projects` is a god class, and `ProjectStorage` a wide interface

`harness/src/dd_harness/projects.py:360` mixes nine areas:

- project lifecycle;
- inventory and documentation;
- researchers;
- repository choice;
- progress and intake;
- document drafts, decisions and answers;
- read models;
- validation;
- the event-sourcing internals (`_fold`, `_append`, `_checked`).

Its Protocol, `ProjectStorage` (`harness/src/dd_harness/storage.py:138`), has about 60 methods.
Each new project feature adds methods to both, so the class can only grow.

### 3. `Conductor._run` is a numbered pipeline in one method

`harness/src/dd_harness/conductor.py:495` runs these steps in order, 454 lines in total:

1. policy gate;
2. payer;
3. input checks;
4. invocation;
5. grounding;
6. validation and storage;
7. project side effects;
8. SHACL;
9. RO-Crate.

Step 7 (marked 7a, 7a′ and 7a″) turns a draft into a version, gives the project a title and records
an entry point. Those are project rules, living inside the conductor.

### 4. Copying between agents

Agents may not import one another, which is right, but no shared home exists for what they have in
common, so it is copied.

- **The agent skeleton.** A private `_abstain()` is byte-identical in six agents, for example
  `agents/advisor-documentation/.../agent.py:882` and `agents/advisor-repository/.../agent.py:52`.
  The evidence item and grounding reference for the agent's input are written out by hand in about
  12 agents. The same helpers exist already, but only in the test kit
  (`harness/src/dd_harness/testing/results.py:21-31`), where production code cannot use them.
  `agents/README.md` tells authors to copy `example-hello`, so every new agent copies the skeleton
  again.
- **Registry access and explainers** (resolved by #977). The policy, repository and standards
  advisers defined the same retrieval types, BM25 tokeniser, FAIRsharing sign-in and
  pinned-download pipeline, and the same `Rationale`, `Explanation` and `TemplateExplainer`. Each
  is now defined once, in `dd_sdk.registry` and `dd_sdk.explain`, with `ModelExplainer`
  parameterised by prompt and identifier pattern; the advisers keep only their records, stop
  words, templates and prompts.

A fix to any of these has to be made in two or three places, and will not be.

### 5. `ConversationHome` does everything

`app/web/src/components/conversation/ConversationHome.tsx` handles:

- URL synchronisation;
- five data loaders, each with its own `AbortController` and loading state;
- live-region announcements;
- attachments and drag-and-drop;
- the turn lifecycle (`deliver`, about 115 lines);
- rendering.

Its test file is 1,848 lines. More widely, every component writes its own fetch-in-effect code, and
the `json<T>()` response helper is copied four times: in `feedback/api.ts`, `project/api.ts`,
`conversation/api.ts` and `run/api.ts`.

### 6. The TypeScript API types are written by hand

`app/web/src/project/api.ts` declares about 40 interfaces copied from the Python models. The golden
fixtures catch a change in what the server sends, but nothing checks the fixtures against those
interfaces. A field renamed in Pydantic updates the fixture while `api.ts` still compiles.

### 7. Lists of members kept by hand

Adding an agent means editing 14 lists in the root `pyproject.toml` and about a dozen other files,
including the Compose files, `app/config/agents.yaml` and `mkdocs.yml`. These lists had already
drifted: `[tool.mypy].mypy_path` was missing seven agents. This change adds them.

### 8. Tests and coverage

- `app/tests/test_app.py` is a 1,597-line catch-all of 69 tests. It mirrors `build_app` and should
  be split with it.
- There is no property-based testing. The code the project owns outright (canonicalisation, the
  policy gate, event replay) is where it would pay most.
- Codecov's patch target is informational, and the per-package floors are deferred (TODO(#243)).
- `harness/tests/test_registry.py:144` relies on a 50 ms sleep to make threads overlap, which may
  fail under load.
- The PostgreSQL conformance tests are skipped silently unless `DD_TEST_POSTGRES` is set. CI sets
  it; a local run does not.

### 9. State that holds only in one process

`Governance` keeps `_turn_locks` and `_started` in memory (`app/src/dd_app/governance.py`, around
lines 131–137). Conversation turns are therefore serialised only within one app process. That is
correct for today's single-process deployment, but no specification states the limit.

## Proposed refactors

These are in order of value against risk. Each should be its own pull request, with tests
written or moved first, so that behaviour is pinned before the code moves.

1. **Split `build_app` into route modules.**
   - Give each area its own module, `dd_app/routes/{projects,conversations,documents,runs,session,...}.py`,
     each exposing `routes(deps) -> list[Route]`. `build_app` keeps only the wiring and the route
     table.
   - Replace hand validation with Pydantic request models, as `reply_answers` already does.
   - Move domain rules (the delete-title check, repository choice) into `Governance` or `Projects`.
   - Forbid handler modules from reaching the store, by making `dd_app.routes` import only
     `dd_app.governance`. Enforce that with an Import Linter `forbidden` contract.
   - Split `test_app.py` along the same lines.
2. **Add a shared agent kit to `dd_sdk`.**
   - `abstain()`, `input_ref()` and `input_evidence()` go in `dd_sdk`, and `dd_harness.testing`
     re-exports them.
   - `dd_sdk.registry` holds `Query`, `Hit`, `SnapshotRef`, `RegistryUnavailable`, the BM25
     tokeniser and the pinned-download pipeline.
   - `dd_sdk.explain` holds `Rationale`, `Explanation`, `TemplateExplainer` and a `ModelExplainer`
     that checks the identifiers it is given back.
   - A FAIRsharing client goes there too, closing #280.

   Then replace "copy `example-hello`" with a generator, `dd.py new-agent`, whose output uses the kit.
3. **Split `Projects` by subdomain.** Make one class per area, all sharing the event log and its fold
   (`_fold`, `_append`). Narrow `ProjectStorage` in the same way, so that a caller depends only on
   the part it uses.
4. **Make `Conductor._run` an explicit pipeline.** Each step becomes a function over a run context,
   and the steps are listed in order in one place. Move the project side effects behind a
   `ProjectEffects` interface that `Projects` implements, so that the conductor no longer holds
   project rules.
5. **Split `ConversationHome` into hooks**: `useProjectDocuments`, `useProjectProgress`,
   `useIntake`, `useAttachments` and `useConversationTurns`. Add one shared `useResource` hook that
   handles aborting and the loading/loaded/failed state, and one shared `json<T>()`.
6. **Type the API boundary.** Generate the TypeScript types from the JSON Schema of the app's
   Pydantic models. As a smaller first step, add a type-level test that each fixture in
   `app/web/fixtures` satisfies its interface.
7. **Split the policy adviser's `run`** into one step per source.
8. **State the single-process limit** of conversation locks in `docs/specs/app.md`, or move the
   locks to the database before running more than one app process.

## Proposed testing measures

- **Hypothesis property tests** for:
  - evidence canonicalisation (the bytes of a registered canonicalisation never change, and
    canonicalising twice gives the same bytes);
  - the contract validators;
  - `Projects` event replay (folding a log gives the same state as applying its events one by one).
- **A loud PostgreSQL skip.** Report the skipped conformance tests in the run summary, and give
  `compose.yaml` a test database so that `DD_TEST_POSTGRES` is easy to set locally.
- **Replace the sleep** in `harness/tests/test_registry.py:144` with an event or barrier.
- **Mutation testing**, scheduled rather than per pull request: a weekly mutmut run over the
  governance modules the project owns (policy gate, grounding linter, evidence hashing), to show
  where tests execute code without checking it.

## Proposed process measures

- Set per-package coverage floors (#243), then make Codecov's patch target blocking.
- Add an eslint-plugin-boundaries rule that feature components do not import one another except
  through an allowed list, so that features do not tangle.
- Record each refactor above as a short decision in `docs/specs`, so that the reason for a module's
  shape outlives the pull request.
- Review the size baseline and the markers below each quarter. The count should fall.

## Checks added with this review

Each check is a ratchet: today's code passes, and the existing excess is recorded where it is, so
it can shrink but not grow.

| Check | Limit | How the existing excess is recorded |
|---|---|---|
| Ruff `C90`, `PLR0911`, `PLR0912`, `PLR0913`, `PLR0915` (Python outside tests) | complexity 15, branches 15, statements 60, arguments 8, returns 8 | `# noqa` at the 23 functions over a limit; RUF100 fails a marker that no longer suppresses anything |
| ESLint `complexity`, `max-depth` (`app/web`, `sdk/browser`, `inventory/browser`, outside tests) | complexity 20, depth 4 | `eslint-disable-next-line complexity` at the 11 functions over the limit; an unused marker is an error |
| `scripts/check_size.py` | 600 lines (Python), 500 (TypeScript) | `scripts/size_baseline.toml` (18 files); an entry may not grow, and a slack or stale one fails |
| `scripts/check_members.py` | each member in every hand-kept list | none: the drift it found (seven agents missing from `mypy_path`) is fixed |

Two things are shared by the checks:

- **Where they run.** The size and registration checks are pre-commit hooks, so they also run in
  CI's "Pre-commit hooks" job on every pull request, including one that changes only TypeScript.
- **Canaries.** Their tests are in `scripts/tests/test_check_size.py`,
  `scripts/tests/test_check_members.py` and `app/web/src/architecture.test.ts`. Each plants a
  violation and expects the check to fail.

The rule for contributors is in CONTRIBUTING.md under "Keeping the code in shape": never add a
marker or a baseline entry to get new code past a check, and remove one when you split the code it
marks.
