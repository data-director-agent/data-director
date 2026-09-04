# Institutional profiles

An institutional profile says what a Data Director instance is allowed to do at this
institution. It is written in YAML so that the people who own the policy, the research data
management team, can read it and propose changes without learning a programming language
(ADR-0003).

## What a profile contains

```yaml
profile_id: default          # referenced from an invocation as policy_bundle_ref: profile:default
version: 1
description: One sentence saying who this profile is for.

agents_enabled:              # only these agents may run; anything else is refused
  - r3.standards-advisor
  - stub.abstain

actions_requiring_approval:  # action classes a human must approve before an agent performs them
  - deposit                  # writing a dataset or metadata record to a repository
  - metadata_write           # changing an existing metadata record
  # "advise" (read-only recommendations, which is all R3 does) is not listed, so R3 runs freely

approved_repositories:       # used by repository recommendation (R1) when it arrives; unused at v0
  - https://orda.shef.ac.uk
pid_systems:                 # persistent identifier systems the institution accepts (R7); unused at v0
  - doi
registries:                  # external registries agents may consult
  fairsharing:
    allowed: true
```

## How it is applied

Every invocation names a profile. Before an agent runs, the conductor checks:

1. Is the agent listed in `agents_enabled`? If not, the invocation **fails** with the problem
   `agent-not-permitted`. Nothing is run.
2. Does the agent's action class appear in `actions_requiring_approval`? If so, the invocation is
   **referred** to the data steward with reason `policy_requires_approval`. Nothing is run.

That is all the gate does. It cannot express conditions ("allow deposit if the dataset is under
1 GB"). If such a rule is ever needed, the profile format will be extended and compiled to a
policy engine's language rather than replaced by it, so this file stays the one stewards read.

## Rights and licensing

When repository selection or deposit arrives, the rights and licensing part of a profile
(which licences may be applied, embargo rules) will be expressed in ODRL, the W3C Open Digital
Rights Language, rather than in ad hoc keys. Nothing in v0 needs it because R3 is read-only and
advisory.

## Files

| File | Purpose |
|---|---|
| `default.yaml` | The profile used when none is named. Enables both v0 agents. |
| `test-restrictive.yaml` | Used by tests: disables R3 and requires approval for advice, to exercise the refused and referred paths. |
