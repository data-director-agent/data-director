# Configuration

Where each setting lives, who reads it, and what to guard. The settings are described where they
are used; this page is the map. On a server the paths are those that
[`deploy/install.sh`](../../../deploy/README.md) creates.

## Layers

A setting has one home, and development has the same tree as a server, rooted at `config/local/` (git-ignored; `uv run scripts/dd.py setup` creates it). On a server, `sudo data-director doctor` checks the deployment against this map and names the fix for each problem ([Deploying to a VM](../../../deploy/README.md)). In development, `dd.py doctor` reports settings files of the old layout (`.env`, `workbench/.env`) and where each moves, and a local `app/config/profile.yaml` that has fallen behind the example (agents omitted, an older `version`, approval actions dropped, an orchestrator it does not enable). Secrets are the exception that matters: a key sits in the one file that
only its own agent can read.

| What | On a server | In development | Read by |
|---|---|---|---|
| What the instance runs: its name, the orchestrator (`model` or `stub`), agents disabled, the address of its [privacy notice](privacy.md) and whether people may use [their own model account](model-broker.md#the-profile-turning-own-accounts-on) | `/etc/data-director/deployment.yaml`, then `sudo data-director apply` | `config/local/deployment.yaml` ([example](../../../config/examples/deployment.yaml)), applied by `dd.py start` | `apply`, which writes the profile (`profile.yaml` beside it, named by `DD_PROFILE`) and the app's agent list (`agents.yaml` beside it, named by `DD_AGENTS_CONFIG`, marking each agent that [calls through the model broker](model-broker.md#the-agents-calling-through-the-broker)), sets or removes `DD_PRIVACY_NOTICE_URL` in `app.env` and, on a server, the units that start the agents |
| The ORCID client, the app's address, problem reports (and the operator, on a development server) | `/etc/data-director/app.env` | `config/local/app.env` ([example](../../../config/examples/app.env)) | The app |
| The workbench's ORCID client, address and admins | `/etc/data-director/workbench.env` ([example](../../../config/examples/workbench.env)) | none: a local workbench signs nobody in | The workbench |
| Settings every agent shares | `/etc/data-director/agents.env` | `config/local/agents.env` ([example](../../../config/examples/agents.env)) | Every agent |
| One agent's own settings, such as `DD_STANDARDS_*` and `DD_MODEL_ID` | `/etc/data-director/agents/<name>.env` | `config/local/agents/<name>.env` ([examples](../../../config/examples/agents/)) | That agent |
| A model key, or the app's ORCID client secret | `/etc/data-director/credentials/<name>/`, root-only, loaded as a systemd credential; an agent's is put there by `sudo data-director secret set` | `config/local/credentials/`, named by `ANTHROPIC_API_KEY_FILE` in the agent's own file | That agent |
| An agent's port | `deploy/agents/<name>.env` in the release | `scripts/run-agents.sh` | The unit, and `agents.yaml` |
| The deployment's own behaviour (repository, branch, releases kept) | `/etc/data-director/deploy.env` | none | `deploy.sh` |
| The admin service's overrides, if any | `/etc/data-director/admin.env` (optional; [the admin service](admin.md)) | none: settings in the environment | The admin service |

The app and the harness hold no model key ([Policy and identity](../../specs/policy-and-identity.md)), so the first two rows never contain one.

## The three files that define an instance

These are policy, not secrets, and are safe to review and to keep under version control.

| File | Sets | Override |
|---|---|---|
| Institutional profile (`app/config/profile.yaml.example`; an instance runs the copy `apply` generates: the example with what `deployment.yaml` sets, and every other key of the example, such as `deposit_transports`, as it stands) | Which agents may run, the action class each is assigned, which classes need approval, and the agent the home page converses with. | `DD_PROFILE` |
| `app/config/agents.yaml` (an instance runs the copy `apply` generates from it, with `model_broker: true` on each agent that calls through the model broker) | Where each agent is, by URL, and which agents call through the model broker. | `DD_AGENTS_CONFIG` |
| `app/config/sources.yaml` | The pinned source copies the source check resolves evidence against. | `DD_SOURCES_CONFIG` |

A fourth file is optional: the MCP servers the harness's tool gateway calls, named by
`DD_TOOLS_CONFIG` ([Agents](../../specs/agents.md#tools-mcp-servers-and-agent-skills)). Without it
there is no gateway, and no agent calls a tool. Each server is listed with the source it serves
and the digest of its tools, which the harness checks at start-up:

```yaml
servers:
  - name: spdx                              # what cards and the profile's tool_servers call it
    url: http://127.0.0.1:8312/spdx/mcp     # its streamable HTTP endpoint (mcp-spdx)
    id_field: licenseId                     # the field that identifies a record
    canonicalisation: dd-spdx-licence-v1    # registered in dd_sdk.evidence
    snapshot_ref: spdx:3.29.0               # optional: the pinned copy it serves
    tools_sha256: "<64 hexadecimal digits>" # from `dd-harness tools pins`, quoted
```

In development, `pid_resolver: true` in `deployment.yaml` sets this up for you: `apply` names
`app/config/tools.yaml` here and grants the Linking Adviser its servers, and `dd.py start` (or
Docker Compose, with `docker/tools.yaml`) runs the PID resolver, an MCP server that resolves
DOIs, ORCID iDs and ROR identifiers ([`mcp-pid/README.md`](../../../mcp-pid/README.md)). A VM
refuses the setting until the server has a unit there.

`DD_REGISTRY_CONTACT` gives Crossref and DataCite an address where they can reach your operators.
The PID resolver and the policy adviser add it to their User-Agent as `mailto:`, which moves their
requests into each registry's identified pool: Crossref's "polite" pool allows 10 lookups a
second rather than 5 ([access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)),
and DataCite 1,000 requests in 5 minutes per IP rather than 500 ([rate limit](https://support.datacite.org/docs/rate-limit)).
Use a shared mailbox for the people who run the deployment, never a person's own address and never
the signed-in researcher's. It says where the operators are, not what the deployment allows, so it
is an environment variable rather than a profile key: set it in the PID resolver's environment
(Docker Compose passes `DD_REGISTRY_CONTACT` from yours) and in the agents' settings file
(`config/local/agents.env`, or `/etc/data-director/agents.env` on a VM; see
[`config/examples/agents.env`](../../../config/examples/agents.env)). Unset, no address is sent; a value that is not one plain address
stops the service at start-up.

The harness needs its `gateway` extra (`data-director-harness[gateway]`) for this file, and an
agent that calls tools needs the SDK's `tools` extra. A server whose tools have changed is
unavailable until you review them and pin the new digest: `dd-harness tools pins` prints each
server's current digest and exits 1 if any differs. A server on a host name or a public address
is `remote`, and the profile's `remote_tool_content` decides which project content may go to an
agent that calls it. The gateway is served at `/mcp` beside the delegation callback; like `/a2a`,
it is for agents on loopback, and NGINX closes it to everyone else.

How long an owner may restore a project they deleted is `DD_PROJECT_RESTORE_DAYS`, in the app's
environment: whole days, 30 if unset, and 0 to make deletion final to the app. The same period
applies to a deleted conversation. Deleting a project or a conversation never removes its record
([Projects](../../specs/projects.md), invariants 25 and 31).

On an app installed on a researcher's own machine, `DD_INVENTORY_FOLDERS` names the folders there
that the app may describe for an inventory: absolute paths, separated by `:` (`;` on Windows). The
researcher may open any folder under them, and the app lists folders by name and runs
`dd-inventory` on the one chosen, read only, following no link; it records nothing until the
researcher checks the inventory and adds it ([Projects](../../specs/projects.md), The inventory
command). Unset, the app describes no folder of its own. The app refuses to start when it is set
and `DD_APP_HOST` is not a loopback address, so a shared deployment never sets it.

How many listings the app runs at once is set in the app's environment, so that slow listings
cannot take the threads a turn needs (#1258). `GET /api/projects`, `/api/conversations` and
`/api/runs` run in a pool of their own: `DD_APP_LISTING_THREADS` is the most that run at once
(whole number, 8 if unset) and `DD_APP_LISTING_QUEUE` the most that may wait for one (16 if
unset, 0 for none). Past both, a listing is answered `503` with a `listing-busy` problem and a
`Retry-After` of `DD_APP_LISTING_RETRY_S` seconds (2 if unset), at once rather than after a long
wait. Turns and run starts use the shared pool of 40 threads, which listings no longer touch. Raise
`DD_APP_LISTING_THREADS` only if the database and the CPU have room; each listing thread competes
with turns for the same process. The app refuses to start if one is not a whole number in range.

Your institution's own data repositories are the profile's `institution_repositories`, which
`apply` copies from `deployment.yaml` as written ([example](../../../config/examples/deployment.yaml)).
Name each by its identifier in the registry that lists it: its re3data identifier (`r3d` and nine
digits), or, since re3data does not list many an institution's repository, its DataCite repository
identifier, which you can find at `https://api.datacite.org/repositories?query=<its name>`. Add
only what no registry holds and you vouch for: `institution_name` and `institution_ror`, where
DataCite registers the repository under a consortium's or a platform's account rather than your
institution's; `data_access_types`, `data_licences` and `charges_deposit_fee`; and the `guidance`
pages you checked them against. The repository advisor offers each to a researcher of your
institution, beyond its shortlist's cap, and cites what you vouch for under the profile's
reference; the project page suggests them first. A repository that neither the pinned re3data
export nor the DataCite snapshot (`app/config/sources.yaml`) holds stops start-up, so a mistyped
identifier is not offered silently ([Deposit](../../specs/deposit.md)).

Your institution's storage for data while a project runs is the profile's `institution_storage`,
which `apply` also copies from `deployment.yaml` as written. No registry lists an institution's
storage, so name each service by a label of your own (`research-filestore`) and give its
`storage_name`, and add what you vouch for: its `storage_kind`, whether it is
`approved_for_sensitive` (left out, it is never taken as approved), whether it
`allows_external_collaborators`, its free `allowance_gb`, whether it is `charges_for_storage`,
what its `storage_backup` is, and the `guidance` pages you checked. The storage adviser recommends
from these alone and cites them under the profile's reference; without them it declines and
points the researcher to your research data staff
([Policy and identity](../../specs/policy-and-identity.md)).

Raise the profile's `version` on every change. Each stored run records the profile and version it
was held to, with the digest of its bytes, so a later reader can tell which rules applied. A
request cannot name a profile; only the operator chooses it
([profiles](../../../workbench/profiles/README.md)). Who the data stewards are is a profile
key too, `stewardship`, which the stewards' team owns and the operator applies, and who administers
the instance is `administrators`; on a VM both are written in `deployment.yaml`
([Becoming a steward](../steward-guide/becoming-a-steward.md)).

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
| `DD_SESSIONS_FILE` | Optional: the SQLite file sessions are kept in, so a restart signs nobody out (the deployment's units set it). Unset, they are kept in memory. |

Sign-in needs HTTPS. Sessions are held in memory, so restarting the app signs everyone out. The
app asks ORCID for the iD and the name only, and keeps no token. A researcher may choose, on a
project's page, facts from their own public ORCID record for its agents; the app then reads that
record from ORCID's public API (`pub.orcid.org`, or `pub.sandbox.orcid.org` for the sandbox
issuer), so the host must be able to reach it. The project's People tab also reads each member's
public name from it; where it cannot be reached, members are shown by their iD. It needs no credential. A deployment made with
`deploy/install.sh` always signs people in: the installer fills `DD_APP_PUBLIC_URL`, waits for the
other settings and the secret (`/etc/data-director/credentials/app/orcid-client-secret`, which the
app's unit loads), and sets up no site password ([Deploying to a VM](../../../deploy/README.md)).
The default session lengths are 8 hours unused and 7 days at most; confirm them against your
institution's policy.

For a workshop or any group session, have each participant sign in with their own ORCID iD. People
who share one sign-in act as one person, and each of them sees all the others' conversations.

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

### The workbench on a server

A deployed workbench signs people in with the same ORCID client and admits only the
administrators the instance's profile names, from `administrators` in `deployment.yaml`
([Deploying to a VM](../../../deploy/README.md#the-workbench)). It runs under the instance's
profile, as the app does. Its settings are in `/etc/data-director/workbench.env`:

| Setting | What it is |
|---|---|
| `DD_OIDC_ISSUER`, `DD_OIDC_CLIENT_ID` | The app's; `install.sh` copies them. The secret is the app's file, loaded by the workbench's own unit. |
| `DD_WORKBENCH_PUBLIC_URL` | Where admins reach it, `https://<host>:8443`. Register `DD_WORKBENCH_PUBLIC_URL/api/sign-in/callback` as a second redirect URI on the ORCID client. |

With no administrator in the profile it does not start. Anyone else who signs in is told they are not an admin, and no session is opened for them. A
workbench without `DD_OIDC_ISSUER`, as on a developer's machine, signs nobody in and acts for the
operator, as before.

## What is stored

| What | Where | Notes |
|---|---|---|
| Each run: input, output, spans, evidence and, by default, a Process Run Crate | `/var/lib/data-director/runs/` (`DD_RUNS_DIR`) | It outlives releases, so back it up with the rest of the host. `DD_WRITE_CRATE=0` stops the crate being written. |
| Each conversation's turn lock | `locks/` under `DD_RUNS_DIR`, or an advisory lock in its database | Lets several app processes share one store. On PostgreSQL each running turn holds one database connection of its own, beside the pool (`DD_POSTGRES_POOL_SIZE`). |
| Each workbench run | `/var/lib/data-director/workbench-runs/` | Apart from the app's runs. |
| Who is signed in | `/var/lib/data-director/app-sessions/`, `workbench-sessions/` (`DD_SESSIONS_FILE`) | A hash of each session identifier, the person's iD and name, and the session's times; no token. Not backed up. |
| Model calls | In the run, as `chat` spans with token counts | No key is ever stored. |
| Records read from a live registry route (FAIRsharing) | Each agent's cache, `/var/cache/data-director-agent-<name>/` (`DD_REGISTRY_CACHE_DIR`; in memory if unset) | Public records only; no token or credential. A record is read again after its time to live (`DD_REGISTRY_CACHE_TTL_RECORD`, `_SEARCH`, `_MISSING`, in seconds; [example](../../../config/examples/agents.env)), and an expired copy answers, marked stale, while the registry is down. Not backed up: `systemctl clean --what=cache data-director-agent@<name>` or `dd-registry-cache clear <file>` empties it. |
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
5. Open the app and read each agent's page in the agent directory: it states what the instance is configured to do.
