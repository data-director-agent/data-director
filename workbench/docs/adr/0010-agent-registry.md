# ADR-0010: Agents are discovered through entry points and described by one manifest

**Status:** Superseded by ADR-0011
**Date:** 2026-09-04

## Context

At v0 `settings.build_conductor` constructed R3 and the stub by name, `cli invoke --agent` listed
them in its help text, the A2A card derived skills from the agents dict, the shell hard-coded two
buttons and one sample, and `shell/uischema.json` described R3's payload. Adding an agent meant
editing five places, three of which had nothing to do with the agent.

The workbench should let a new agent kind be added by creating one package and one registration,
in-tree or in a separate distribution, without editing the conductor, linter, CLI, transports or
shell.

## Decision

1. Agents are found through Python entry points in the group `workbench.agents`. Each entry
   point names a factory `build(settings) -> Agent`. In-tree agents are registered in the
   workbench's own `pyproject.toml`; a package outside this repository registers the same way.
2. `workbench.registry.Registry` loads them (`from_entry_points`) or takes a list
   (`from_agents`, for tests). A duplicate `agent_id` or an object that does not satisfy the
   `Agent` protocol is a `RegistryError`. A factory that raises `NotImplementedError` marks an
   agent that is registered but not usable; the registry records the reason and continues (R3,
   until ported). Any other exception from a factory is a configuration error and propagates.
3. An agent is an `AgentSpec` plus `run`. The spec carries identity, version, description,
   requirement identifiers, action class, accepted input classes, grounding mode, payload class
   and an optional RJSF fragment for its payload. `agents.base.describe(spec)` renders the one
   manifest entry that the A2A agent card, `workbench agents`, `GET /agents` and the shell's
   agent picker all consume.
4. Harness settings (`Settings`) hold only harness concerns: runs directory, profiles directory,
   whether to write a crate. Each agent reads its own `DD_<AGENT>_*` environment variables in its
   own factory.
5. The shell composes its UI schema per render: the envelope-level base from `shell/uischema.json`
   plus the payload fragment from the manifest entry of the envelope's `agent_id`. Nothing is
   merged server-side; a replayed run renders with its own agent's fragment.

Rejected: an explicit `AGENTS = {...}` module (one line too, but a central file every agent
author edits, and unusable for out-of-tree packages); profile-driven discovery (profiles already
gate `agents_enabled` as *policy*; conflating discovery with permission would let a profile edit
add code paths); LinkML slot annotations as rendering hints (moves presentation into the fixed
contract, an ADR per hint).

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `importlib.metadata.entry_points` | Runtime path (standard library) | `Registry.from_agents` with an explicit list; the registry is the only reader of entry points. |

## Consequences

- Adding an agent: a package under `src/workbench/agents/<name>/` (or elsewhere), a `build`
  factory, one line in `pyproject.toml`, `uv sync`, a sample input, a uischema fragment if it has
  a payload, tests marked with the requirements they exercise, and the agent's id in the profiles
  that should enable it. See `src/workbench/agents/README.md`.
- `uv sync` is needed after adding an entry point; `tests/test_registry.py` fails with a message
  saying so if the installed metadata is stale.
- The policy gate still decides, per profile, which registered agents may run. Registration is
  not permission.
