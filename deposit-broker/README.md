# Data Director deposit broker

Holds each researcher's own repository token, sealed, and creates a **draft** deposit for the
harness when it presents a deposit grant ([Deposit](../docs/specs/deposit.md), *Depositing
through an API*). It never publishes: it asks Zenodo only for the `deposit:write` scope, which
cannot publish, and no code path calls the publish action.

The app and the harness never see a token. The browser connects an account here directly,
through the reverse proxy, which passes on only `/deposit-broker/connect/`:

- **Connect through OAuth.** The person chooses *Connect Zenodo*, signs in at Zenodo and approves
  depositing. The broker keeps the tokens sealed.
- **Paste a token.** Where the deployment has no OAuth application, the person creates a personal
  token with only the `deposit:write` scope and pastes it in. It is checked with one call before
  it is kept.

The harness asks for a draft on the broker's loopback address (`POST /deposits`), with a
short-lived grant naming the person (by a sealed pseudonym), the repository and the digests of
exactly what they approved.

```bash
uv run dd-deposit-broker serve            # 127.0.0.1:8310
```

```bash
DD_DEPOSIT_BROKER_TRY_TOKEN=… uv run dd-deposit-broker try   # make and delete one sandbox draft
```

Settings are described in `src/dd_deposit_broker/settings.py` and in
[the operations guide](../docs/guide/operations/deposit-broker.md).

It imports only the SDK, and nothing imports it.
