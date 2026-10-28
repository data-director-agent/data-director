# ADR-0026: A model key stays with the agent that calls the model

**Status:** Proposed; amended by [ADR-0027](0027-no-agent-in-the-apps-process.md)
**Date:** 2026-10-22

Amends [ADR-0011](0011-remote-agents.md) (the manifest gains `models`).

## Context

An agent that calls a hosted model needs an API key. Until now only the standards advisor's
optional explainer (`DD_STANDARDS_EXPLAINER=anthropic`) used one. A model-backed orchestrator (#21)
makes a model call the normal path, not an option. The way the key reached the explainer had five
faults (#133):

- **The SDK found the key for itself.** The explainer built `anthropic.Anthropic()` with no
  arguments, so the SDK searched its own credential chain: `ANTHROPIC_API_KEY`, then other
  variables, then a command-line login saved in the user's home directory. Nobody could say from
  the configuration which credential a run had used.
- **A missing key failed every run, not start-up.** The agent started and advertised itself, and
  then each run failed at the model call.
- **Every agent got the key.** `scripts/run-agents.sh` loaded one `workbench/.env` for every agent
  it started.
- **The app could hold it.** The app runs the standards advisor in its own process
  (`app/src/dd_app/governance.py`). An explainer configured there would have put the key in the
  same process that serves the web page, the API and the delegation callback.
- **Nobody could see that data left.** No manifest said that an agent sends its input to a
  hosted model, or to which provider.

Blueprint C1 asks for secrets to be handled under a recognised security baseline (#43). C2 asks
that what leaves the institution be declared and controllable (#40).

## Decision

1. **Only the calling agent's process holds the key.** The app, the harness and the conductor
   never hold it. It never travels in an A2A message, a grant, an envelope, a span, an evidence
   item, an RO-Crate or an export.
2. **An agent in another component's process may not call a hosted model.** The app runs the
   standards advisor in its own process only without a model. It refuses at start-up if that
   advisor is configured for one. To use a model, a deployment runs the agent as its own
   service, and the app's agent list names it (`name: standards`). The app then reaches it over
   A2A like any other agent.
3. **One way to supply the key in development, and one in deployment.**
   `dd_sdk.credentials.api_key` reads it once, when the agent's factory builds it:
   - In development: `ANTHROPIC_API_KEY`.
   - In deployment: `ANTHROPIC_API_KEY_FILE`, a path to a file holding the key. A relative path
     is resolved against `$CREDENTIALS_DIRECTORY`, which is where systemd's `LoadCredential=`
     puts the file. An absolute path suits a container secret.

   A model provider other than Anthropic uses the same rule under its own variable name.
4. **The key is passed explicitly.** The agent hands the key to the model client itself. No
   model client may be built without one, so the provider SDK's own credential chain is never
   searched. A command-line login (`ant auth login`) is not supported.
5. **A configuration error stops start-up, in one line.** Each of these is a `ConfigError`, which
   names the variable or the path and never the key's value:
   - both variables set, or neither;
   - an unreadable file, or an empty one;
   - an unknown setting.

   `dd_sdk.serve.main` prints the error as one line and exits with status 2 before any port
   opens. Agent units do not restart on that status (`RestartPreventExitStatus=2`). The app
   treats the error the same way.
6. **Each agent has its own environment.** In development, `scripts/run-agents.sh` gives each
   agent `workbench/agents/<name>.env` on top of the shared `workbench/.env`, so a key in one
   agent's file reaches no other agent. In deployment, each agent unit reads
   `/etc/data-director/agents/<name>.env`, and its key arrives as a systemd credential, readable
   only by that unit. All agents run as one user, so a key file readable by that user would be
   readable by every agent.
7. **Sharing keys.** A deployment may give several agents one key. It should give each agent a
   key of its own, so that one key can be revoked without the others and the provider's usage
   reports show each agent separately. A spending limit is set on the provider's side, for the
   Console workspace the key belongs to, not per key. A deployment that wants a limit per agent
   needs one workspace per agent.
8. **The manifest says what is sent where.** `AgentSpec.models` lists each model the agent sends
   data to, as configured: `provider`, `model` and `hosting` (`hosted` or `local`). It names no
   credential. The key is optional in a description, and a card written before this ADR is read
   as declaring no model, so the contract version does not change. The app's About tab shows the
   list, or says that the agent calls no model.
9. **Tests and CI never need a real key.** A model call in a test is replayed from a cassette,
   with `--record-mode=none --block-network` as now. The root `vcr_config` removes credential
   headers from any cassette that is recorded. A test runs a model-backed agent against a
   cassette with a sentinel key, and checks that the sentinel appears in no stored file and in
   no manifest.

TODO(#40): a profile rule that refuses an agent's `models`, per data class, enforced by the
conductor from the manifest before a run is sent.

## Dependencies introduced

None. `LoadCredential=` is part of systemd from version 247 onwards; Ubuntu 22.04 has 249.

## Consequences

- An agent that calls a model checks its key when it starts, and refuses to start without one.
  A deployment can no longer appear healthy while every model-backed run fails.
- The standards advisor's model mode needs a service of its own in deployment
  (`data-director-agent@standards`). Its default template mode still runs in the app's process
  and needs no key.
- `models` is what the deployment configured, declared by the agent itself. It is not proof.
  #40 decides how a profile enforces it.
- A new model-backed agent, such as #21's orchestrator, takes its key through
  `dd_sdk.credentials.api_key` in its factory, and declares the model in `AgentSpec.models`.
  Building a model client with no key, or reading a key during a run, revisits this decision.
- Rotating a key means replacing the credential file and restarting that agent's unit. No other
  component changes.
