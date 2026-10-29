# ADR-0031: The ecosystem and its repository boundaries

**Status:** Proposed
**Date:** 2026-10-28

## Context

The `data-director-agent` organisation is meant to hold a range of open, community-developed
resources for agentic research data stewardship: agents, Agent Skills, MCP servers, evaluation
sets and tooling. Today this repository holds all the code. It is a uv workspace of separate
packages (ADR-0011, ADR-0022): `sdk`, `harness`, `workbench`, `app` and one package per agent.
The organisation also holds `classmark`, an experiment in classifying datasets with a calibrated
model, which does not use the contract.

Three facts constrain when and how to split:

- **The contract still changes often.** Thirty ADRs in, the core contract is at 0.8.0, and
  agent-owned classes (ADR-0019) arrived recently. While that holds, a contract change made across
  several repositories needs a coordinated pull request in each, where in one repository it needs
  one.
- **Nothing is installable from outside.** No package is on a package index, so a repository
  outside this one cannot depend on the SDK.
- **The packages are already separable in principle.** Every agent requires only `sdk` at run
  time, and the harness reaches each agent over A2A at a URL (ADR-0011), so an agent can be served
  from anywhere. In practice, however, the workspace installs every member together, which hides
  undeclared ties: agents' tests import the harness and each other, one agent's `src/` imports
  the workbench, and several tests read files elsewhere in the repository (#274, #275).

Not every resource the organisation will hold depends on the contract. An Agent Skill, an MCP
server over a public registry or an evaluation set can be used by any agent framework.

## Decision

1. **Two kinds of resource.** A resource is *contract-bound* if it imports `dd_sdk` or speaks
   the Data Director contract: the SDK, the harness, the workbench, the app and A2A agents. It is
   *framework-neutral* otherwise: Agent Skills, MCP servers, evaluation sets, vocabulary snapshots
   and libraries usable without the contract.

2. **Contract-bound resources stay in this repository** until they meet the criteria in §5.
   New agents are added under `agents/` as now.

3. **Framework-neutral resources may live in their own repositories from the start**, but a
   repository is created only when its first real content is ready to commit (#280). The
   organisation does not hold empty placeholder repositories.

4. **Each workspace member keeps to its own directory.**
   - Its `src/` imports only the first-party packages it declares in `[project].dependencies`
     (or an extra).
   - Its `tests/` import only those and the packages in its own `[dependency-groups].dev`.
   - No Python file in it reads a path outside its directory.

   `scripts/check_boundaries.py` enforces this in CI (#274). An exception is listed in that
   check's allow-list with the issue that removes it (#275).

5. **A package leaves this repository when all of these hold:**
   - it has maintainers beyond the core team, or needs a release cadence of its own;
   - it requires only packages published to a package index, with bounded versions (#276, #277);
   - it does something real, with evaluations behind it (ADR-0013);
   - it passes the boundary check with no exceptions.

   It moves with its history (`git filter-repo`) to a repository of its own, and is registered
   by URL like any other remote agent. The SDK and the harness move last, if at all, and not
   before the contract reaches 1.0 (TODO(#260)).

6. **Repositories in the organisation are named by kind:**
   - `agent-<name>` for an A2A agent;
   - `mcp-<name>` for an MCP server;
   - a single `skills` repository for Agent Skills, serving also as a plugin marketplace.

   Libraries and experiments take a plain descriptive name, as `classmark` does.

7. **A capability is kept apart from the agent that uses it.** Where an agent's work is useful
   without the contract, such as a lookup in a public registry, that work is built as a
   framework-neutral library or MCP server, and the agent is a thin wrapper that adds the
   contract: classes, grounding, evidence. Whether agents are also reached over MCP is not
   decided here (TODO(#280)).

8. **Experiments are marked as experiments.** A repository that evaluates an approach without
   committing to it, such as `classmark`, says so in its README and in the organisation profile.
   Work from it enters the ecosystem as a capability under §7.

## Dependencies introduced

None.

## Consequences

- A contract change remains one pull request while the contract is young.
- Community contributions that do not need the contract (skills, MCP servers) have somewhere to
  go without learning it.
- Each member has to declare the packages its tests import, which the workspace did not require
  until now, and the boundary check fails a pull request that adds an undeclared tie.
- Moving a package out becomes mechanical once it meets §5. Repositories outside this one still
  need the SDK on a package index (#277), a template (#278) and shared CI (#279).
- A future contributor must not start an organisation repository with no content, nor move a
  contract-bound package out before it meets §5, without revisiting this decision.
