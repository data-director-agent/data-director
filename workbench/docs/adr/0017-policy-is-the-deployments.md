# ADR-0017: The institutional profile belongs to the deployment, and assigns each agent its class

**Status:** Accepted (amends ADR-0003)
**Date:** 2026-09-25

## Context

ADR-0003 made the institutional profile a steward-readable YAML file and the policy gate a small
function over it. Three things the gate relied on were set by the wrong party.

- **The caller chose the profile.** `InvocationRequest.policy_bundle_ref` named it, and
  `load_profile` accepted `profile:<id>` or any filesystem path. The A2A and AG-UI endpoints
  accept requests from anyone who can reach them, so a caller could send
  `profile:test-permissive`, or point at any YAML file on the host, and so choose its own rules.
- **The agent chose its own action class.** The gate matched the `action_class` on the agent's
  card. An agent that declared `advise` was never referred, whatever it did.
- **Some keys did nothing.** `approved_repositories`, `pid_systems` and `registries` were loaded
  and read by nothing, and agents never received them. A steward editing them changed nothing.

Blueprint C12 asks for institutional policies to be enforced, and C13 for irreversible actions to
be blocked without human confirmation. Neither holds if the party being governed chooses the
rules. The workbench already follows a rule for the fields an agent must not decide about itself
(identifiers, timestamps, lineage): the conductor sets them. This ADR applies that rule to policy.

## Decision

- **One profile per deployment.** The operator names the profile file when the conductor is
  built: `DD_PROFILE` (default `profiles/default.yaml`), or `--profile <path>` on `workbench
  invoke` and `workbench serve`. The profile is loaded once. A malformed profile stops start-up
  (`PolicyError`), not a request. Every invocation, including every delegated child, is gated by
  it.
- **A request cannot name a profile.** `policy_bundle_ref` is removed from `InvocationRequest`.
  The request schema is closed, so a request that still carries it fails validation and nothing
  runs.
- **The envelope records what was applied.** `Envelope` gains `policy_bundle_ref`
  (`profile:<profile_id>@v<version>`) and `policy_digest` (the SHA-256 of the profile file's
  bytes), both filled by the conductor and both required. A stored run therefore names exactly
  the rules it was held to, even after the file changes.
- **The profile assigns each agent its action class.** `agents_enabled` (a list) is replaced by
  `agents`, a mapping from `agent_id` to the action class the steward assigns it. The gate
  refuses an agent not listed (`failed(agent-not-permitted)`), refuses an agent whose card
  declares a class other than the one assigned (`failed(action-class-mismatch)`, 403), and
  matches the assigned class against `actions_requiring_approval`. The card's `action_class`
  stays as the agent's declaration; it is checked, not trusted.
- **A profile says only what something enforces.** The vocabulary is `profile_id`, `version`,
  `description`, `agents`, `actions_requiring_approval`. Any other key is refused at load.
  Approved repositories (R1), persistent identifier systems (R7) and registry access return as
  keys with the agent or check that enforces them, each with its own ADR amendment.
- **Approval is unchanged for now.** An action class requiring approval is still
  `referred(policy_requires_approval)` to `data_steward`, and nothing resumes it. TODO: the
  approval half of the gate (suspend, record an approval bound to the input hash and the
  `policy_digest`, resume as a new invocation) is issue #16.

## Dependencies introduced

None.

## Consequences

- A caller of the A2A or AG-UI endpoint can no longer weaken the policy. Running two policies
  means running two workbench instances.
- An agent that changes its declared action class stops running until a steward updates the
  profile. That is intended: a change in what an agent does is a policy decision.
- Tests choose a profile by building their conductor with one (`make_conductor(..., profile=)`),
  not by putting it in a request.
- Envelopes stored before this change have no `policy_bundle_ref` or `policy_digest` and do not
  validate against the new schema.
- The gate decides whether the workbench calls an agent. It cannot stop an agent's own service
  doing something it did not declare. TODO: when agents that write arrive, an agent proposes the
  write in its payload and the conductor performs it after approval, so no agent holds write
  credentials (Blueprint P4: "AI agents may draft and suggest"). That needs its own ADR.
- TODO: per-user or per-group profiles need an authenticated user (C1), which the workbench does
  not yet have.
- A future contributor must not reintroduce a way for a request, or an agent, to select or relax
  the profile applied to it without revisiting this decision.
