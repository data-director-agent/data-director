# The deposit broker

The deposit broker lets a researcher deposit a **draft** of their dataset in a repository through
its API, with their own account there, after they approve it on the project's Deposit tab. It is a
separate service. It holds each person's repository token, sealed, and makes the repository's API
calls itself. Neither the app nor the harness, nor any agent, ever holds a token. The design is in
[Deposit](../../specs/deposit.md), *Depositing through an API*.

Zenodo is the only repository it deposits to so far. The shipped Zenodo override sends drafts to
**the Zenodo sandbox**, `sandbox.zenodo.org`, a test copy of Zenodo whose records and DOIs are not
real, so a practice deployment never makes a real record.

!!! warning "Alpha, and off by default"
    Without the deposit broker every repository is deposited to by hand, as before. The broker
    never publishes: it asks Zenodo only for the `deposit:write` scope, which lets it create drafts
    and upload files but not publish them, and no code path calls Zenodo's publish action. The
    researcher adds the data files and publishes in Zenodo's own interface.

## What it does

When a person approves a deposit, the harness:

1. checks that the package is the project's newest, built from a valid report, and that nothing
   it was built from has changed;
2. renders the approved DataCite record as Zenodo's deposition metadata, and keeps it beside the
   package;
3. records `deposit_approved` in the project log;
4. signs a **deposit grant**: a short-lived token naming the person (by a sealed pseudonym), the
   repository, the API root and the SHA-256 digests of exactly what was approved;
5. sends the grant, the metadata and the package to the broker on loopback;
6. records `deposit_recorded`, with the draft's address, or `deposit_failed`, with a reason code.

The broker checks the grant (its signature, audience, lifetime and that it is used once), checks
that the bytes it was sent are the ones the grant names, finds the person's token, creates the
draft, and uploads the RO-Crate package to it. If the upload fails it deletes the half-made draft.
Every refusal and every repository error is reduced to a reason code, so a repository's own error
text, which might quote what was sent, never leaves it.

## Connecting an account

A person connects their own account on the Settings page, under *Repository accounts*, in one of
two ways:

- **Connect through OAuth.** They choose *Connect your Zenodo sandbox account*, sign in at the
  sandbox, approve depositing, and come back. This needs an OAuth application registered for the
  deployment (below).
- **Paste a personal token.** They create a token on the sandbox under *Applications*, *Personal
  access tokens*, with only the `deposit:write` scope, and paste it. The broker checks it with one
  call before it keeps it. This works with no OAuth application.

Each person needs an account on `sandbox.zenodo.org`, which is separate from `zenodo.org`.
Disconnecting erases the token at once.

## On a VM

`deploy/install.sh` prepares the broker but does not start it:

- the user `data-director-deposit-broker`, which no other service shares;
- `/etc/data-director/credentials/deposit-broker/`, readable by root alone, with an empty
  `oauth-clients` (`{}`);
- `/etc/data-director/deposit-broker.env`, with the sandbox as the only API root it may call, and
  its public address and the app's, from `--domain`;
- the unit `data-director-deposit-broker.service`, which keeps its store in
  `/var/lib/data-director-deposit-broker/`, readable by the broker's user alone, and listens on
  `127.0.0.1:8310`;
- an NGINX location passing `/deposit-broker/connect/` to it, and nothing else of it.

### 1. The broker's secrets

As root:

```bash
cd /etc/data-director/credentials/deposit-broker
```

```bash
(umask 077 && openssl rand -base64 32 > key-encryption-key)
```

```bash
(umask 077 && openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt > subject-key)
```

The key-encryption key seals every token at rest. The subject key opens the pseudonym sealed in
each grant; the harness is given its public half.

### 2. The harness's side

Deposit grants are signed with the model grants' signing key and name the person by the same
pseudonym, so the app needs `model-grant-signing-key` and `pseudonym-secret` in
`/etc/data-director/credentials/app/` ([The model broker](model-broker.md#the-harness-signing-grants)),
whether or not the model broker runs. Add the deposit broker's public subject key beside them:

```bash
cd /etc/data-director/credentials/app
```

```bash
(umask 077 && openssl ec -in ../deposit-broker/subject-key -pubout > deposit-broker-subject-key)
```

Then, in `/etc/data-director/app.env`:

```bash
DD_DEPOSIT_BROKER_URL=http://127.0.0.1:8310
DD_APP_DEPOSIT_BROKER_URL=/deposit-broker
```

Run `sudo data-director apply`, which loads the subject key into the app's drop-in.

### 3. An OAuth application (optional)

Without one, people paste a token. To let them sign in at the sandbox instead, sign in to
`https://sandbox.zenodo.org`, open *Applications*, *Developer applications*, *New application*,
and register:

- **Redirect URI**: `https://<your domain>/deposit-broker/connect/zenodo/callback`;
- **Client type**: confidential.

Write its client ID and secret into the broker's credentials, keyed by the API root:

```bash
sudoedit /etc/data-director/credentials/deposit-broker/oauth-clients
```

```json
{"https://sandbox.zenodo.org/api": {"client_id": "…", "client_secret": "…"}}
```

### 4. Check, then start

`dd-deposit-broker try` makes one draft on the sandbox with a personal token and deletes it again,
which shows the broker can reach Zenodo and the token works:

```bash
DD_DEPOSIT_BROKER_TRY_TOKEN=… /opt/data-director/current/.venv/bin/dd-deposit-broker try
```

```bash
sudo systemctl enable --now data-director-deposit-broker.service
```

```bash
sudo systemctl restart data-director.target
```

The profile must offer the transport. The reference profile does
(`deposit_transports: [zenodo]`, [Institutional profiles](../../../workbench/profiles/README.md));
a profile without it deposits by hand.

## Moving from the sandbox to Zenodo

The sandbox is set in two places, on purpose: the Zenodo override's `deposit.base_url`
([`app/config/repositories/overrides/zenodo.yaml`](../../../app/config/repositories/overrides/zenodo.yaml))
and the broker's `DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS`. A grant naming an API root the broker does
not allow is refused, so a deployment cannot reach the real Zenodo by a change to one of them alone.
Moving is a decision for the research data team, TODO(#648).

## In development

```bash
uv run dd-deposit-broker serve
```

with the settings in `deposit-broker/src/dd_deposit_broker/settings.py`, and in the app's
environment `DD_DEPOSIT_BROKER_URL`, `DD_DEPOSIT_BROKER_SUBJECT_KEY`, the model-grant signing key
and pseudonym secret, and `DD_APP_DEPOSIT_BROKER_URL=/deposit-broker`. The Vite dev server passes
`/deposit-broker/connect/` on to the broker as NGINX does.
