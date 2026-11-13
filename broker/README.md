# Data Director model broker

A separate service that lets a person's own AI provider account pay for model calls, so that no
agent, and neither the app nor the harness, ever holds that person's key. The design is in
[A person's own model account](../docs/specs/model-accounts.md); running it is in
[The model broker](../docs/guide/operations/model-broker.md).

The broker:

- holds each person's provider key, sealed with AES-256-GCM under a key-encryption key only it
  reads, with the person's pseudonym bound in as associated data (`dd_broker.seal`);
- knows a person only by a pseudonym, which reaches it sealed inside a model grant
  (`dd_broker.grants`);
- makes a model call only for an agent that proves who it is with its own broker credential and
  presents a grant the harness signed for that agent, before the grant expires, for a model the
  grant allows;
- decides from the grant alone whose account pays, and says so on every answer
  (`X-DD-Model-Account: own` or `deployment`);
- reduces every refusal and provider error to a status and a reason code, keeps no prompt and no
  reply, and counts tokens per pseudonym and day (`dd_broker.store`);
- refuses a custom base URL unless the operator allow-listed it, and one that resolves to a
  private or reserved address unless the operator said so (`dd_broker.guard`).

It is alpha and off by default: until the profile turns own accounts on (TODO(#810)) every call is
paid for by the deployment, as before. The harness mints the grants (`dd_harness.model_grants`)
and every model-backed agent can call through the broker (`dd_sdk.credentials.model_endpoint`). The
browser's enrolment interface is TODO(#807); OpenAI-compatible accounts are TODO(#811).

```bash
uv run dd-model-broker serve        # 127.0.0.1:8300; settings in dd_broker.settings
```
