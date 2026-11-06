# Configuration

Where each setting lives, who reads it, and what to guard. The settings are described where they
are used; this page is the map. On a server the paths are those that
[`deploy/install.sh`](../../../deploy/README.md) creates.

## Layers

A setting has one home, and development has the same tree as a server, rooted at `config/local/` (git-ignored; `uv run scripts/dev.py setup` creates it). `dev.py doctor` reports settings files of the old layout (`.env`, `workbench/.env`) and where each moves, and a local `app/config/profile.yaml` that has fallen behind the example (agents omitted, an older `version`, approval actions dropped, an orchestrator it does not enable). Secrets are the exception that matters: a key sits in the one file that
only its own agent can read.

| What | On a server | In development | Read by |
|---|---|---|---|
| The ORCID client, the app's address, problem reports (and the operator, on a development server) | `/etc/data-director/app.env` | `config/local/app.env` ([example](../../../config/examples/app.env)) | The app |
| Settings every agent shares | `/etc/data-director/agents.env` | `config/local/agents.env` ([example](../../../config/examples/agents.env)) | Every agent |
| One agent's own settings, such as `DD_STANDARDS_*` and `DD_MODEL_ID` | `/etc/data-director/agents/<name>.env` | `config/local/agents/<name>.env` ([examples](../../../config/examples/agents/)) | That agent |
| A model key, or the app's ORCID client secret | `/etc/data-director/credentials/<name>/`, root-only, loaded as a systemd credential | `config/local/credentials/`, named by `ANTHROPIC_API_KEY_FILE` in the agent's own file | That agent |
| An agent's port | `deploy/agents/<name>.env` in the release | `scripts/run-agents.sh` | The unit, and `agents.yaml` |
| The deployment's own behaviour (repository, branch, releases kept) | `/etc/data-director/deploy.env` | none | `deploy.sh` |

The app and the harness hold no model key ([Policy and identity](../../specs/policy-and-identity.md)), so the first two rows never contain one.

## The three files that define an instance

These are policy, not secrets, and are safe to review and to keep under version control.

| File | Sets | Override |
|---|---|---|
| Institutional profile (`app/config/profile.yaml.example`, or your `profile.yaml`) | Which agents may run, the action class each is assigned, which classes need approval, and the agent the home page converses with. | `DD_PROFILE` |
| `app/config/agents.yaml` | Where each agent is, by URL. | `DD_AGENTS_CONFIG` |
| `app/config/sources.yaml` | The pinned source copies the source check resolves evidence against. | `DD_SOURCES_CONFIG` |

Raise the profile's `version` on every change. Each stored run records the profile and version it
was held to, with the digest of its bytes, so a later reader can tell which rules applied. A
request cannot name a profile; only the operator chooses it
([profiles](../../../workbench/profiles/README.md)).

## Who a run acts for

The app can sign people in with ORCID, so that each run acts for the person who started it and
records that ORCID vouched for them ([Policy and identity](../../specs/policy-and-identity.md)). Register an ORCID public API client for the
deployment, with the redirect URI `https://<your host>/api/sign-in/callback`, then set:

| Variable | What it is |
|---|---|
| `DD_OIDC_ISSUER` | `https://orcid.org` |
| `DD_OIDC_CLIENT_ID` | The client's ID (`APP-…`) |
| `DD_OIDC_CLIENT_SECRET_FILE` | A file that holds the client's secret, relative to `$CREDENTIALS_DIRECTORY` under systemd |
| `DD_APP_PUBLIC_URL` | `https://<your host>`, as registered |
| `DD_SESSION_IDLE_S`, `DD_SESSION_LIFETIME_S` | Optional: a session ends after 8 hours unused or 7 days at most |

Sign-in needs HTTPS. Sessions are held in memory, so restarting the app signs everyone out. The
app asks ORCID for the iD and the name only, and keeps no token. A deployment made with
`deploy/install.sh` always signs people in: the installer fills `DD_APP_PUBLIC_URL`, waits for the
other settings and the secret (`/etc/data-director/credentials/app/orcid-client-secret`, which the
app's unit loads), and sets up no site password ([Deploying to a VM](../../../deploy/README.md)).
The default session lengths are 8 hours unused and 7 days at most; confirm them against your
institution's policy.

On a development server, without `DD_OIDC_ISSUER`, nobody signs in. `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` are then
required, every run acts for this operator, whoever uses the page, and the banner says on every
page that nobody is signed in. Use an ORCID iD URL as the identifier where the operator has one.
Setting both a provider and an operator stops the app at start-up.

## What is stored

| What | Where | Notes |
|---|---|---|
| Each run: input, output, spans, evidence and, by default, a Process Run Crate | `/var/lib/data-director/runs/` (`DD_RUNS_DIR`) | It outlives releases, so back it up with the rest of the host. `DD_WRITE_CRATE=0` stops the crate being written. |
| Model calls | In the run, as `chat` spans with token counts | No key is ever stored. |
| Problem reports | A public GitHub issue, if a credential is set | Off without a GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` and `DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`) or a token (`DD_FEEDBACK_GITHUB_TOKEN`), not both. Either needs Issues: write on one repository and nothing else. |

## Before you open it to users

1. Check that sign-in works (above): sign in with an ORCID iD, and confirm that a request with no
   session is answered 401 (`curl -i https://<your host>/api/agents`).
2. Review the profile. List only the agents you intend to offer, and add to
   `actions_requiring_approval` any action that must be referred to a person.
3. Decide on [AI models](ai-models.md): whether either model-backed agent is on, which model, and
   whose key. Tell users when the answer is yes, since their conversation then goes to a
   provider.
4. Confirm the app and agent ports are on loopback or a private network.
5. Open the app and read each agent's About tab: it states what the instance is configured to do.
