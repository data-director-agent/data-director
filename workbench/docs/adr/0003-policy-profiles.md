# ADR-0003: Institutional policy as declarative YAML profiles; policy engines deferred

**Status:** Accepted
**Date:** 2026-09-04

## Context

Blueprint C12 and C13 require institutional governance policies to be enforced and irreversible
actions to be blocked without human confirmation. The people who own those policies are data
stewards in the Library's research data management team, not engineers. Policy engines (Open
Policy Agent's Rego, Cedar) are expressive but introduce a second language every contributor must
learn and stewards cannot read.

## Decision

- An institutional profile is a YAML file under `profiles/` with a small fixed vocabulary:
  `profile_id`, `version`, `agents_enabled`, `actions_requiring_approval`,
  `approved_repositories`, `pid_systems`, `registries`. The README in that directory is written
  for stewards.
- The conductor's policy gate (`workbench.policy`) is bespoke and small: it answers "may this
  agent run?" and "does this agent's action class require approval?". A refused agent yields a
  `failed` outcome with problem `agent-not-permitted`; an action needing approval yields
  `referred(policy_requires_approval)` to `data_steward`. It does nothing else.
- Policy engines are **rejected for v0**. If genuinely conditional logic appears (a rule that
  depends on the dataset, the requester, or another rule), the YAML is compiled to Rego rather than
  replaced by it, so the steward-readable file stays authoritative.
- The rights and licensing subset of a profile will be expressed in ODRL when repository selection
  or deposit arrives. Nothing in v0 needs it; the README says so.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `pyyaml` | Runtime path | Profiles are plain mappings and lists; `ruamel.yaml` or a JSON rendering of the same profile is a drop-in. |
| OPA / Cedar | Rejected | — |

## Consequences

- Stewards can read and, with review, edit the profile.
- Every new gate question is a schema addition to the profile and a few lines in `policy.py`.
- The gate is deliberately incapable of expressing conditional logic; that is the trip-wire for
  revisiting this decision.
