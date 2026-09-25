# Institutional profiles

An institutional profile says what a Data Director instance is allowed to do at this
institution. It is written in YAML so that the people who own the policy, the research data
management team, can read it and propose changes without learning a programming language
(ADR-0003).

## Which profile applies

A deployment applies one profile to every invocation. The operator chooses it when starting the
workbench: `DD_PROFILE=profiles/default.yaml`, or `--profile` on `workbench invoke` and
`workbench serve`. A request cannot name a profile, so whoever sends one cannot choose their own
rules (ADR-0017). Each stored run records the profile it was held to as
`policy_bundle_ref: profile:<profile_id>@v<version>`, with `policy_digest`, the SHA-256 of this
file's bytes, so a later reader can tell exactly which rules applied.

TODO: per-user or per-group profiles. These need an authenticated user (C1), which the workbench
does not yet have.

## What a profile contains

```yaml
profile_id: default
version: 2                   # raise it on every change, so stored runs say which rules applied
description: One sentence saying who this profile is for.

agents:                      # only these agents may run, each with the action class you assign it
  r3.standards-advisor: advise
  stub.abstain: advise

actions_requiring_approval:  # action classes a human must approve before an agent performs them
  - deposit                  # writing a dataset or metadata record to a repository
  - metadata_write           # changing an existing metadata record
  # "advise" (read-only recommendations, which is all R3 does) is not listed, so R3 runs freely
```

Those five keys are the whole vocabulary. A profile with any other key is refused when the
workbench starts, so a misspelt or out-of-date key cannot look as if it were in force.

## How it is applied

Before an agent runs, the conductor checks:

1. Is the agent listed under `agents`? If not, the invocation **fails** with the problem
   `agent-not-permitted`. Nothing is run.
2. Does the agent declare the action class this profile assigns it? Each agent states its own
   class, but the class that counts is yours. If the two differ (for example, an agent upgraded
   from `advise` to `metadata_write`), the invocation **fails** with the problem
   `action-class-mismatch` until you update the profile. Nothing is run.
3. Does the assigned class appear in `actions_requiring_approval`? If so, the invocation is
   **referred** to the data steward with reason `policy_requires_approval`. Nothing is run.
   There is not yet a way to approve a referred run and let it continue; see issue #16.

That is all the gate does. It cannot express conditions ("allow deposit if the dataset is under
1 GB"). If such a rule is ever needed, the profile format will be extended and compiled to a
policy engine's language rather than replaced by it, so this file stays the one stewards read.

The gate decides whether the workbench calls an agent. It cannot stop an agent's own service
from doing something it did not declare. When agents that write arrive, they will propose the
write and the workbench will carry it out after approval, so that an agent holds no write
credentials of its own (ADR-0017).

## Planned keys

These arrive with the agent that enforces them, and not before:

- approved repositories, for repository recommendation (R1);
- accepted persistent identifier systems (R7);
- which external registries agents may consult.

## Rights and licensing

When repository selection or deposit arrives, the rights and licensing part of a profile
(which licences may be applied, embargo rules) will be expressed in ODRL, the W3C Open Digital
Rights Language, rather than in ad hoc keys. Nothing in v0 needs it because R3 is read-only and
advisory.

## Files

| File | Purpose |
|---|---|
| `default.yaml` | The profile applied when `DD_PROFILE` is unset. Enables every in-tree agent. |
| `test-permissive.yaml` | Used by tests: enables the in-tree agents and the test doubles. |
| `test-restrictive.yaml` | Used by tests: enables only the stub, assigns `quality.reviewer` a class it does not declare, and requires approval for advice, to exercise the refused, mismatched and referred paths. |
