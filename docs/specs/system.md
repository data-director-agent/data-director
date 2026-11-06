# System and boundaries

## Intent and scope

Data Director is built as separate packages in one uv workspace, so that each can be installed,
deployed and eventually moved on its own. This spec says what each package is for, what it may
depend on, which way the dependencies run, and when a package may leave this repository. It also
fixes what the word "harness" names.

| Member | Distribution | What it is |
|---|---|---|
| `sdk/` | `data-director-sdk` | What agents and the harness share: the core contract, evidence, span helpers and the A2A agent server. |
| `harness/` | `data-director-harness` | The governance of an invocation: conductor, policy gate, input check, grounding linter, source check, run store and provenance, its A2A way in, and its test kit. Deployable. |
| `workbench/` | `data-director-workbench` | The development way in to the harness: CLI, viewer, AG-UI transport, evaluation, and a development configuration. Not deployed. |
| `app/` | `data-director-app` | The Data Director app that researchers use. A way in to the harness. |
| `agents/<name>/` | `data-director-agent-<name>` | One package and one A2A service per agent ([Agents](agents.md)). |
| `inventory/` | `data-director-inventory` | The command a researcher runs where their data live to describe a dataset's files ([Projects](projects.md)). |

The contract, transport, grounding and the app's own process boundary are specified elsewhere:
[Contract](contract.md), [Transport and tracing](transport.md),
[Evidence and grounding](grounding.md), [The app](app.md).

## Invariants

1. The dependency graph between members at run time is:
   - `sdk` depends on no other member;
   - `harness` depends on `sdk` only;
   - `workbench` and `app` depend on `harness` and `sdk`, and on nothing else in the workspace;
   - each agent depends on `sdk` only;
   - `inventory` depends on no other member.

   The graph is what each member declares in `[project].dependencies`; no check compares the
   declarations with this list, so a new first-party dependency is a change to this spec.
   Import Linter contracts in the root `pyproject.toml` (`uv run lint-imports`, CI) fail an
   import, direct or indirect, that runs against the direction above: the layers `sdk`,
   `harness`, then `workbench`, `app` and each agent, with no agent importing another and
   `inventory` importing no member. A known exception is an `ignore_imports` entry naming the
   issue that removes it. `scripts/check_boundaries.py` (CI) fails code that imports a member it
   does not declare, and `scripts/check_wheels.py` (CI) installs each built wheel alone and
   imports it. Invariants 2 and 3 test the two edges most likely to be added by mistake.
2. Nothing under `harness/src/` imports the workbench, the app, any agent package or Inspect AI.
   Enforced by `harness/tests/test_harness_boundary.py`.
3. Nothing under `app/src/` imports the workbench or any agent package. The app reaches every
   agent over A2A through the conductor and registers no agent object in its own process.
   Enforced by `app/tests/test_app_boundary.py`; detail in [The app](app.md).
4. No agent runs in the process of the harness or of a way in to it, except in tests, where
   `dd_harness.testing.in_process` serves the agent over A2A on an in-memory transport so the
   real wire is exercised.
5. Each member keeps to its own directory:
   - a module under its `src/` imports only first-party packages it declares in
     `[project].dependencies` or an extra;
   - any other Python file in it (tests, scripts) may also import those in its own
     `[dependency-groups].dev`;
   - no Python file in it reads a path outside its directory.

   Enforced by `scripts/check_boundaries.py` in CI. Each known exception is listed in
   `scripts/boundaries.toml` with the issue that removes it; an exception that no longer occurs
   fails the check, so the list only shrinks. Do not add an exception to let a new tie pass.

   The checks run together in the CI job "Architecture", which "CI passed" requires.
   `workbench/tests/test_architecture_canary.py` plants a violation of each kind (direction,
   undeclared import, read outside the member) in a copy of the repository and fails unless the
   check reports it, so a misconfigured check cannot pass silently.
   TODO(#497): add a canary for a cycle in `app/web` when its checks exist.
6. The harness ships no deployment configuration: no institutional profile, agent list or source
   list, and no default run directory. Every path comes from its `DD_*` variable or from a default
   the caller passes; with neither, start-up stops with `SettingsError`. No harness module
   computes a configuration path from its own location (`harness/src/dd_harness/settings.py`).
   The test kit's own profiles are the one exception, and they serve tests only.
7. Each way in brings its own configuration: the workbench's development set lives in
   `workbench/`, the app's reference set in `app/config/`. A `DD_*` variable overrides any file,
   so a deployment replaces configuration without changing the repository.
8. A name in `sdk/` or `harness/` for something the harness does says "harness", never
   "workbench": the delegation callback variable `DD_HARNESS_URL`, the harness's A2A agent card,
   the SDK's delegate class, the default trace `service.name` (`data-director-harness`) and the
   core schema's identity (`https://w3id.org/data-director/schema/core`). No alias for an older
   "workbench" name is kept. "Workbench" names only the workbench: its CLI, its development
   configuration and its viewer.
9. Test module basenames are unique across the workspace, because test directories are not
   packages and pytest imports each module by its basename (root `pyproject.toml`, pytest
   configuration).

## Boundaries and contracts

**The harness is a library with one way in of its own.** Each way in (the workbench, the app,
the harness's A2A endpoint) builds a conductor and calls it; the conductor alone fills
identifiers, timestamps and lineage ([Orchestration](orchestration.md)). `dd-harness serve`
serves the A2A routes and agent card and nothing else, for a deployment that needs no viewer;
`uvicorn` is an optional extra so that a way in which embeds the conductor does not install it.
`workbench serve` builds the same conductor and adds AG-UI and the viewer. The CLI stays with the
workbench.

**The test kit belongs to the harness.** The scripted doubles, the in-memory agent server and
the test profiles are `dd_harness.testing`, in the deployable package beside the code they
exercise, so a test of an agent or of a way in needs nothing from the workbench.

**The workbench contains neither agent code nor governance code.** It is a test bed for people
who write agents. The app must not depend on it.

**Agents are separate services.** The harness reaches each agent over A2A at a URL from
configuration, so an agent can be served from this repository or from anywhere else; the
mechanics are in [Agents](agents.md) and [Transport and tracing](transport.md).

**Documents are kept with what they describe.** A package's own design notes are in its
`docs/`; what governs every package (the specs, contract, glossary, requirements register and
review record) is in the repository-level `docs/`.

**The organisation and its repositories.** A resource is *contract-bound* if it imports `dd_sdk`
or speaks the Data Director contract: the SDK, the harness, the workbench, the app and A2A
agents. It is *framework-neutral* otherwise: Agent Skills, MCP servers, evaluation sets,
vocabulary snapshots and libraries usable without the contract.

- Contract-bound resources live in this repository. A new agent is added under `agents/`.
- A framework-neutral resource may have its own repository from the start, but a repository is
  created only when its first real content is ready to commit. The organisation holds no empty
  placeholder repositories.
- Where an agent's work is useful without the contract (a lookup in a public registry, say), that
  work is built as a framework-neutral library or MCP server, and the agent is a thin wrapper
  that adds the contract: classes, grounding and evidence.
- A repository that evaluates an approach without committing to it (such as `classmark`) says it
  is an experiment in its README and in the organisation profile. Its work enters the ecosystem
  as a capability under the previous rule.
- Repositories are named by kind: `agent-<name>` for an A2A agent, `mcp-<name>` for an MCP
  server, and one `skills` repository for Agent Skills, which is also a plugin marketplace.
  Libraries and experiments take a plain descriptive name.

**When a package leaves this repository.** All of these must hold:

- it has maintainers beyond the core team, or needs a release cadence of its own;
- it requires only packages published to a package index, with bounded versions. Not possible
  yet: nothing is published (TODO(#277)) and versions between members are not bounded
  (TODO(#276));
- it does something real, with evaluations behind it ([Evaluation and conformance](evaluation.md));
- it passes the boundary check with no exception.

It then moves with its history to a repository of its own and is registered by URL like any
other remote agent. The SDK and the harness move last, if at all, and not before the contract
reaches 1.0.

## Rationale

The harness was once packaged inside the workbench. The app, which must not depend on a
development tool, could then not reach the harness, so its runs were neither checked nor
recorded nor attributed. With the harness on its own, every way in, the product included, is
governed identically, and a deployment installs the SDK and harness without the viewer, Inspect
AI or development configuration.

Configuration belongs to the deployment, as the institutional profile does
([Policy and identity](policy-and-identity.md)). A default derived from the harness's own
location silently ties a deployment to the repository's development files.

Keeping each member to its own directory makes the separation real. The workspace installs
every member together, so an undeclared import or a read of a sibling's files passes every test
and fails only when the member is installed alone. The boundary check and the wheel check catch
those ties before they accumulate.

Contract-bound packages stay together because the contract still changes often: a contract
change in one repository is one pull request, across several it is one per repository, made in
step. Framework-neutral resources carry no such cost and can be used by any agent framework, so
contributors who do not need the contract should not have to learn it.

"Workbench" in a harness name misleads the people who operate or integrate a deployment, which
uses the harness without the workbench.

## Rejected alternatives

- **Leaving the harness inside the workbench.** The app could not use it without depending on a
  development tool.
- **The app running an agent in its own process.** It is a second way of reaching an agent with
  behaviour that diverges from A2A (a protobuf `Struct` turns integers into floats, so payloads
  differed and tests did not see it). It also needed special rules for model keys and a second
  agent list. One path, A2A, for every agent.
- **Splitting contract-bound packages into their own repositories now.** Every contract change
  would need coordinated pull requests, and nothing is installable from a package index.
- **Placeholder repositories for planned resources.** They signal work that does not exist.
- **Aliases for the old "workbench" names.** Every user of those names was in this repository and
  every package is alpha, so a clean rename cost less than carrying both.
- **Giving the harness its own CLI.** The harness is a library with an A2A endpoint; a CLI for
  developers is the workbench's job.

## Non-functional requirements

- **Security.** Calls between the harness and its agents, and to the harness's own server, are
  not authenticated yet (TODO(#17, #43)). Until they are, agent ports and the harness server must
  not be exposed beyond the host or a trusted private network.
- **Portability.** Each member builds a wheel that installs and imports alone (invariant 1).

## Open questions

- TODO(#275): remove the remaining boundary exceptions. The standards advisor's evaluations and
  test kit import the workbench and the harness from its `src/`; most agents' tests read samples
  from `workbench/samples`; the app reads its revision from the repository root; several
  repository-level tests sit in `workbench/tests`.
- TODO(#225): whether configuration may come from one file rather than four variables, how the
  source list pins a source copy stored outside the repository, and how a steward edits and
  reviews the profile in a deployment.
- TODO(#170): whether the read-side views of runs and conversations belong to the harness server.
- TODO(#255): some shared documentation (`docs/contract.md`, the requirements register) and
  `agents/README.md` still say "the workbench" where they mean the harness.
- TODO(#3): whether `https://w3id.org/data-director/schema/core` is registered with w3id.
- TODO(#260): the criteria for the contract, and so the SDK and harness, reaching 1.0.
- TODO(#280): the first framework-neutral repositories, and whether agents are also reached over
  MCP.
