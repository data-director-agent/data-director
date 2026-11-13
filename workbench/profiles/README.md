# Institutional profiles

An institutional profile says what a Data Director instance is allowed to do at this
institution. It is written in YAML so that the people who own the policy, the research data
management team, can read it and propose changes without learning a programming language
([Policy and identity](../../docs/specs/policy-and-identity.md)).

## Which profile applies

A deployment applies one profile to every invocation. The operator chooses it when starting the
workbench: `DD_PROFILE=profiles/default.yaml`, or `--profile` on `workbench invoke` and
`workbench serve`. A request cannot name a profile, so whoever sends one cannot choose their own
rules ([Policy and identity](../../docs/specs/policy-and-identity.md)). Each stored run records the profile it was held to as
`policy_bundle_ref: profile:<profile_id>@v<version>`, with `policy_digest`, the SHA-256 of this
file's bytes, so a later reader can tell exactly which rules applied.

TODO(#154): per-user or per-group profiles. These need an authenticated user (C1), which the workbench
does not yet have.

## What a profile contains

```yaml
profile_id: default
version: 2                   # raise it on every change, so stored runs say which rules applied
description: One sentence saying who this profile is for.

agents:                      # only these agents may run, each with the action class you assign it
  advisor.standards: advise
  example.hello: advise

actions_requiring_approval:  # action classes a human must approve before an agent performs them
  - deposit                  # writing a dataset or metadata record to a repository
  - metadata_write           # changing an existing metadata record
  # "advise" (read-only recommendations, which is all the standards advisor does) is not listed, so the standards advisor runs freely

orchestrator: orchestrator.stub  # optional: the agent a person converses with in the app; it must be
                             # listed under `agents`. Without it the app offers no conversation.

hosted_models:               # optional: the classes of project content an agent that calls a
  - inventory                # hosted model may be given; `documentation` is the other. Without
                             # this key only `inventory` may (docs/specs/projects.md, invariant 8)

model_accounts:              # optional: whose model account pays; see "People's own model
  own: off                   # accounts" below. Without this key, as with `own: off`, the
                             # deployment pays for every model call
```

Those eight keys are the whole vocabulary. A profile with any other key is refused when the
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

4. In a project, if the agent's card declares a `hosted` model, are all the classes of project
   content it would be given listed under `hosted_models`? If not, the invocation **fails** with
   the problem `project-content-withheld`. Nothing is sent to the agent.

5. If the profile lets people use their own model account, the grant each model-backed agent is
   sent says so, and the model broker pays for its calls as the next section describes. In a
   project, an agent that may call a person's own endpoint counts as calling a `hosted` model for
   step 4, unless every endpoint the profile allows is declared `local`.

That is all the gate does. It cannot express conditions ("allow deposit if the dataset is under
1 GB"). If such a rule is ever needed, the profile format will be extended and compiled to a
policy engine's language rather than replaced by it, so this file stays the one stewards read.

The gate decides whether the workbench calls an agent. It cannot stop an agent's own service
from doing something it did not declare. When agents that write arrive, they will propose the
write and the workbench will carry it out after approval, so that an agent holds no write
credentials of its own ([Policy and identity](../../docs/specs/policy-and-identity.md)).

## People's own model accounts

`model_accounts` decides whether the people using this instance may pay for its model calls with
their own AI provider account, in place of the deployment's
([A person's own model account](../../docs/specs/model-accounts.md)). A person adds their account
on the app's Profile page. Their key goes to the model broker and nowhere else.

```yaml
model_accounts:
  own: allowed               # off, allowed or required
  fallback: deployment       # deployment or none: who pays for someone with no account of their own
  providers:                 # the providers a person's own account may be with
    - provider: anthropic
      base_urls:             # optional: other addresses the account may name
        - url: https://llm.example.ac.uk
          local: true        # optional: this address is not a hosted service
```

| `own` | `fallback` | Someone with an account of their own | Someone without one |
|---|---|---|---|
| `off` | (leave out) | The deployment pays. | The deployment pays. |
| `allowed` | `deployment` | They pay. | The deployment pays. |
| `allowed` | `none` | They pay. | The run fails with `model-account-missing`. |
| `required` | `none` | They pay. | The run fails with `model-account-missing`. |

If their provider refuses their key or reports a limit, the run fails. The deployment's key is
never used instead.

The profile is refused when the workbench or the app starts if it:

- combines `own: required` with `fallback: deployment`, which contradict each other;
- sets `fallback` or `providers` with `own: off`, where nothing would apply them;
- turns own accounts on without `fallback` or without at least one provider;
- names a provider other than `anthropic` (OpenAI-compatible providers are TODO(#811));
- lists a base URL that is not a plain `https` address;
- has any other key under `model_accounts`.

Turning own accounts on also needs the operator to have set up model grants and the broker
([The model broker](../../docs/guide/operations/model-broker.md)); otherwise the app or the
workbench stops at start-up rather than appear to apply a rule it cannot.

`hosted_models` still decides what project content may go to an agent that calls a hosted model.
A person's own account calls their provider's service, which is hosted. Declare a base URL
`local: true` only if it is a service your institution runs. While own accounts are on, an agent
counts as calling a hosted model unless every address the profile allows is declared local.

## Planned keys

These arrive with the agent that enforces them, and not before:

- approved repositories, for repository recommendation (R1). What each repository requires is
  not a key here but a requirement set ([Deposit](../../docs/specs/deposit.md)); the approved list is #320;
- accepted persistent identifier systems (R7);
- which external registries agents may consult.

## Rights and licensing

When repository selection or deposit arrives, the rights and licensing part of a profile
(which licences may be applied, embargo rules) will be expressed in ODRL, the W3C Open Digital
Rights Language, rather than in ad hoc keys. Nothing in v0 needs it because the standards advisor is read-only and
advisory.

## Files

| File | Purpose |
|---|---|
| `default.yaml` | The profile the workbench applies when `DD_PROFILE` is unset. Enables every in-tree agent. |

The test profiles, `test-permissive.yaml` and `test-restrictive.yaml`, belong to the harness's test
kit and are in [`../../harness/src/dd_harness/testing/profiles/`](../../harness/src/dd_harness/testing/profiles/).
