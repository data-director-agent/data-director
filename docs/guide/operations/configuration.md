# Configuration

Where each setting lives, who reads it, and what to guard. The settings are described where they
are used; this page is the map. On a server the paths are those that
[`deploy/install.sh`](../../../deploy/README.md) creates.

## Layers

A setting has one home, and development has the same tree as a server, rooted at `config/local/` (git-ignored; `uv run scripts/dev.py setup` creates it). `dev.py doctor` reports settings files of the old layout (`.env`, `workbench/.env`) and where each moves. Secrets are the exception that matters: a key sits in the one file that
only its own agent can read.

| What | On a server | In development | Read by |
|---|---|---|---|
| The operator's identity, the app's address, problem reports | `/etc/data-director/app.env` | `config/local/app.env` ([example](../../../config/examples/app.env)) | The app |
| Settings every agent shares | `/etc/data-director/agents.env` | `config/local/agents.env` ([example](../../../config/examples/agents.env)) | Every agent |
| One agent's own settings, such as `DD_STANDARDS_*` and `DD_MODEL_ID` | `/etc/data-director/agents/<name>.env` | `config/local/agents/<name>.env` ([examples](../../../config/examples/agents/)) | That agent |
| A model key | `/etc/data-director/credentials/<name>/`, root-only, loaded as a systemd credential | `config/local/credentials/`, named by `ANTHROPIC_API_KEY_FILE` in the agent's own file | That agent |
| An agent's port | `deploy/agents/<name>.env` in the release | `scripts/run-agents.sh` | The unit, and `agents.yaml` |
| The deployment's own behaviour (repository, branch, releases kept) | `/etc/data-director/deploy.env` | none | `deploy.sh` |
| Who may use the site | `/etc/nginx/data-director.htpasswd` | none | NGINX |

The app and the harness hold no model key (ADR-0026), so the first two rows never contain one.

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

`DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` are required, and the app will not start without them.
Until people sign in (#17), every run acts for this operator, whoever uses the page, and the page
says so. Use an ORCID iD URL as the identifier where the operator has one.

## What is stored

| What | Where | Notes |
|---|---|---|
| Each run: input, output, spans, evidence and, by default, a Process Run Crate | `/var/lib/data-director/runs/` (`DD_RUNS_DIR`) | It outlives releases, so back it up with the rest of the host. `DD_WRITE_CRATE=0` stops the crate being written. |
| Model calls | In the run, as `chat` spans with token counts | No key is ever stored. |
| Problem reports | A public GitHub issue, if a token is set | Off without `DD_FEEDBACK_GITHUB_TOKEN`; the token needs Issues: write on one repository and nothing else. |

## Before you open it to users

1. Set the operator in `app.env`, and the site's password in NGINX. These are the only access
   controls until #17.
2. Review the profile. List only the agents you intend to offer, and add to
   `actions_requiring_approval` any action that must be referred to a person.
3. Decide on [AI models](ai-models.md): whether either model-backed agent is on, which model, and
   whose key. Tell users when the answer is yes, since their conversation then goes to a
   provider.
4. Confirm the app and agent ports are on loopback or a private network.
5. Open the app and read each agent's About tab: it states what the instance is configured to do.
