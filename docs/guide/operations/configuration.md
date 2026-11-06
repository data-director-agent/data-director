# Configuration

Where each setting lives, who reads it, and what to guard. The settings are described where they
are used; this page is the map. On a server the paths are those that
[`deploy/install.sh`](../../../deploy/README.md) creates.

## Layers

A setting has one home, and development has the same tree as a server, rooted at `config/local/` (git-ignored; `uv run scripts/dd.py setup` creates it). On a server, `sudo data-director doctor` checks the deployment against this map and names the fix for each problem ([Deploying to a VM](../../../deploy/README.md)). In development, `dd.py doctor` reports settings files of the old layout (`.env`, `workbench/.env`) and where each moves, and a local `app/config/profile.yaml` that has fallen behind the example (agents omitted, an older `version`, approval actions dropped, an orchestrator it does not enable). Secrets are the exception that matters: a key sits in the one file that
only its own agent can read.

| What | On a server | In development | Read by |
|---|---|---|---|
| The ORCID client, the app's address, problem reports (and the operator, on a development server) | `/etc/data-director/app.env` | `config/local/app.env` ([example](../../../config/examples/app.env)) | The app |
| Settings every agent shares | `/etc/data-director/agents.env` | `config/local/agents.env` ([example](../../../config/examples/agents.env)) | Every agent |
| One agent's own settings, such as `DD_STANDARDS_*` and `DD_MODEL_ID` | `/etc/data-director/agents/<name>.env` | `config/local/agents/<name>.env` ([examples](../../../config/examples/agents/)) | That agent |
| A model key, or the app's ORCID client secret | `/etc/data-director/credentials/<name>/`, root-only, loaded as a systemd credential; an agent's is put there by `sudo deploy/secret.sh set` | `config/local/credentials/`, named by `ANTHROPIC_API_KEY_FILE` in the agent's own file | That agent |
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

### Trying sign-in against the ORCID sandbox

To test sign-in without real iDs, on a development server or on your own machine, use the ORCID
sandbox, a separate system with its own accounts and iDs. It is not backed up and may be wiped.

1. Create a sandbox account at <https://sandbox.orcid.org/register>. The sandbox sends email only
   to `@mailinator.com` addresses, which are public inboxes that anyone can read: choose a name
   nobody would guess, use a throwaway password, and read the verification email at
   <https://www.mailinator.com>. Verify the address; the developer tools stay closed until you do.
2. Register a client under *Developer tools* in the sandbox, through ORCID's
   [sandbox registration page](https://info.orcid.org/register-a-client-application-sandbox-member-api/).
   Give it the redirect URI the app will send, which is `DD_APP_PUBLIC_URL` followed by
   `/api/sign-in/callback`:

   | Where the app runs | `DD_APP_PUBLIC_URL` | Redirect URI to register |
   |---|---|---|
   | Your machine | `http://127.0.0.1:7860` | `http://127.0.0.1:7860/api/sign-in/callback` |
   | A development server | `https://<your host>` | `https://<your host>/api/sign-in/callback` |

   ORCID's support advises `127.0.0.1` rather than `localhost` for a local client. ORCID matches
   the URI exactly, character for character: scheme, host, port and path.
3. Set `DD_OIDC_ISSUER=https://sandbox.orcid.org`, `DD_OIDC_CLIENT_ID`, the client's secret (as a
   file or `DD_OIDC_CLIENT_SECRET`), and `DD_APP_PUBLIC_URL` as in the table. Leave
   `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` empty. Restart the app.
4. Open the app at the address in `DD_APP_PUBLIC_URL`, not at another name for the same machine.
   The sign-in cookie belongs to one host, so starting at `localhost:7860` and returning to
   `127.0.0.1:7860` fails.

A client belongs to the sandbox account that registered it, and only that account can change its
redirect URIs. Register one client per instance, so that a developer's local address is never
added to a shared server's client.

If sign-in fails, the page gives one message for every cause. The reason is in the app's log, on
the line that starts `data-director: sign-in refused:`.

| Symptom | Cause and fix |
|---|---|
| ORCID's own page says `redirect_uri … does not match for registered client` | The app sent an address the client does not list. Compare `DD_APP_PUBLIC_URL` with the registered URI, and check that a leftover value from another environment is not set. |
| `this sign-in was not started in this browser` | The cookie did not come back: you started on a different host name, or the browser refuses `Secure` cookies over plain HTTP (Chrome and Firefox allow it for `127.0.0.1`; Safari does not). |
| `the sign-in has expired or was already used` | The app restarted between starting and finishing, which `--reload` does on any code change, or the callback address was reloaded. Start again. |
| `the provider refused the code` | The client secret is not the one for this client, or belongs to production rather than the sandbox. |

A production client takes the same settings with `DD_OIDC_ISSUER=https://orcid.org` and an
`https` redirect URI, and does not accept `http://127.0.0.1`.

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
