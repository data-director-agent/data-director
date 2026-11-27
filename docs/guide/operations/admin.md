# The admin service

The admin service is a read-only web view of one deployment, for the people who run it. It
gathers what an operator otherwise reads from several commands, and the runs and projects people
have made, in one place. It changes nothing: every change is still made on the VM's command line,
and each page names the command.

## Reaching it

It listens on the VM's loopback address, port 8200, and NGINX does not serve it. From your own
machine, open a tunnel over SSH and leave it running:

```bash
ssh -N -L 8200:127.0.0.1:8200 you@data-director.example.ac.uk
```

then open <http://localhost:8200>. Use another local port if 8200 is taken on your machine
(`-L 9200:127.0.0.1:8200`, then <http://localhost:9200>). To keep the tunnel in your SSH config,
and to reach the LLM gateway's UI and Grafana the same way, see
[Reaching the admin interfaces over SSH](tunnels.md).

It has no sign-in. Whoever can open an SSH session to the VM can reach it, and could read the same
stores and files there already: SSH access is its credential. Three things keep it there:

- `dd-admin serve` refuses to listen on any address that is not loopback;
- it answers 421 to a request whose `Host` is not `localhost` or a loopback address, so a web page
  open in your browser cannot reach it through your tunnel (DNS rebinding);
- its pages run no script, are not cached, and cannot be framed.

Do not proxy it through NGINX or open port 8200 in the firewall. For a page to be reachable from
elsewhere it would need a sign-in, which it does not have (#154).

## What it shows

| Page | Shows | Read from |
|---|---|---|
| Overview | Health, the running commit, agents up, host memory, swap and load (amber below 600 MB available or at half the swap), people active, runs and projects over 7 and 30 days, runs per day, outcomes, the latest runs | All of the below |
| Operations | Each problem `data-director doctor` finds, with its fix; its notes and what it skipped; the releases on disk, which is live and which failed to start; each unit's state, restarts and last 100 journal lines | `data-director doctor --json`, run as the service's user; `/opt/data-director`; `systemctl show`; `journalctl` |
| Agents | Each agent in `agents.yaml`: whether its card answers, its unit, version, action class and models; the card in full | Each agent's `/.well-known/agent-card.json` |
| People | Everyone a run acted for or who created a project: their runs, conversations and projects, and when they were first and last seen | The run and project stores |
| Runs | Every run, newest first, by agent, outcome, person, project or conversation; a run's outcome, who it acted for, telemetry, estimated cost and envelope | The run store |
| Spend | Spend this month against an optional budget; spend over the last 30 days by day, model and gateway key; the tokens runs recorded over 30 days by model, agent, person and project, with their estimated cost | The LLM gateway's `/spend/logs/v2` and `/model/info`; the run store |
| LLM gateway | Whether the gateway is ready and its database connected; each model with its upstream, prices and limits; each key, team and user with its spend against its budget, its period and rate limits | The gateway's `/health/readiness`, `/model/info`, `/key/list`, `/team/list` and `/user/list` |
| Model broker | Whether the broker answers and its unit's state; people's own accounts counted by provider; tokens over 30 days by day, model and who paid; which agents hold a broker credential, and which model-backed agents do not; who the deployment pays for; `model-broker.env` | The broker's `/healthz` and `/admin/summary`; `systemctl show`; the agents' cards; `/etc/data-director` |
| Monitoring | Links to Grafana, Prometheus, Alertmanager, the LLM gateway's own page and Langfuse; whether each answers; the alerts Prometheus is firing and Alertmanager holds | Each service's health and alerts endpoints, at the addresses in `DD_ADMIN_*_URL` |
| Policy | The profile as the harness parses it: the agents it allows with their action class, which wait for a person, tool servers and settings; what a hosted model or remote tool may receive; whose account pays; administrators, steward teams and who is admitted; the roster compared with the profile and `deployment.yaml` | `/etc/data-director/profile.yaml` and `deployment.yaml`; the agents' cards; the app's `/api/about` |
| Escalations | Each steward team's live escalations, who has taken them, how long each has waited and which are overdue to be sent to the team again | The project store, for the teams the profile names |
| Security | The security events services record, by event, outcome and service, over the last day or week | The journal of the deployment's units |
| Projects | Every project: who created it, its documents and repository; a project's event log and runs | The project store |
| Download case | On a run, a project, and the runs of one conversation: everything recorded about it, as a case for a developer to debug | The run and project stores; the journal if asked |
| Configuration | The files under `/etc/data-director`, each with the command that changes it; the stores' locations and the live profile | `/etc/data-director`; the app's `/api/about` |
| Feedback | A link to the feedback issues | `DD_FEEDBACK_REPO` |

The stores, the doctor, the broker, the escalation queues and the security events are read at most
once a minute, the monitoring services and the profile every 30 seconds, and the gateway every
five minutes; **Refresh** reads them again.

### Spend

Spend comes from the optional LLM gateway ([deploy/llm-gateway](../../../deploy/llm-gateway/README.md)),
when the agents call their models through it. The page keeps two figures apart:

- **The gateway's**, which LiteLLM priced as each call was made: the month to date, the last
  30 days by day, by model and by gateway key (one key per agent, or one key for the
  [model broker](model-broker.md) when it pays for the deployment's calls).
- **An estimate from the runs**: the tokens each run's agent reported (`telemetry.model_calls`),
  priced at the gateway's own per-token prices. Only this one can say which person or project the
  tokens were for, so the person, project and run pages show it too. It differs from the
  gateway's figure when an agent calls a model without the gateway, when something else uses the
  gateway, and by discounts such as cached input. Tokens on a model the gateway has no price for
  are counted as unpriced, not as free. A call a person's own model account paid for, as the run
  records it (`model_account: own`), is left out of the estimate, as it is of the gateway's figure.

Without the gateway the page still shows the tokens runs recorded, without prices.
`DD_ADMIN_MONTHLY_BUDGET` sets a budget that the overview and the page show the month's spend
against, amber from 80 % and red once reached; it stops nothing, as the gateway's key, user and
team budgets do. Setting the gateway up for the page is in its
[README](../../../deploy/llm-gateway/README.md#the-admin-services-spend-page).

The doctor runs as the service's user, `datadirector`, so the checks that need root are listed
as skipped: the secrets, the backups directory and `nginx -t`. Run `sudo data-director doctor` on
the VM for those. A fix the doctor names that refers to "the clone" means the clone you installed
from.

The service keeps no list of accounts: people are known only from the runs and projects that name
them. Who may use the workbench is the profile's `administrators`, set in `deployment.yaml` ([Configuration](configuration.md)).

### LLM gateway

The gateway page shows how the optional LLM gateway ([deploy/llm-gateway](../../../deploy/llm-gateway/README.md))
allows and limits model calls; Spend shows what they cost. It reads with the same read-only key
as Spend, so a gateway set up for one is set up for both. A key is shown by its alias, never by
the key or its hash. A budget is green below 80 %, amber from 80 % and red once reached; the gateway
itself stops a key, team or user at its budget. Each section names the
`deploy/llm-gateway/scripts/admin.py` command, or the `config.yaml` change, that alters it. If the
key cannot read a list, the page says which and shows the rest.

### Model broker

The broker page shows the optional [model broker](model-broker.md). The broker's store is
readable by its own user alone, so the page asks the broker for an aggregate,
`GET /admin/summary`, with a credential only this service holds: people's own accounts counted by
provider, and tokens summed over everyone by day, model and who paid. It never names a person or
their pseudonym, and carries no account label or key. To give the service that credential, and
the broker its digest, run as root from your clone:

```bash
sudo deploy/broker-admin-credential.sh
```

It writes `credentials/admin/model-broker-admin` and `credentials/model-broker/admin-credential`,
the drop-ins that load them and set `DD_ADMIN_BROKER_URL`, and restarts both services. Run it
again to replace the credential, or with `--remove` to take it away. Without it, the page still
says whether the broker answers, its unit's state and its settings file.

The page also compares the agents that hold a broker credential with those whose cards declare
models: a model-backed agent without one cannot call through the broker
(`deploy/broker-credentials.sh`).

### Monitoring

The LLM gateway's optional `monitoring` profile ([deploy/llm-gateway](../../../deploy/llm-gateway/README.md#monitoring-optional))
runs Prometheus, Alertmanager and Grafana, each on the VM's loopback address, so a link to one
works only through an SSH tunnel ([Reaching the admin interfaces over SSH](tunnels.md)) or at an
address you publish. The page links to each. A service without a setting is linked at its tunnel
address (`localhost:3000`, `9090`, `9093`) and is not asked. One with a setting is asked from the
service, so the address can be one the VM reaches, and the page shows whether it answers and lists
its alerts: the ones Prometheus is firing or pending, and the ones Alertmanager holds. The
overview counts the firing ones. Grafana ships with no dashboard and no data source: add
Prometheus at `http://prometheus:9090`, as the gateway's README describes. Alertmanager sends its
alerts nowhere until you add a receiver.

The gateway's own page (`/ui` on `DD_ADMIN_LITELLM_URL`) and Langfuse, if you run it
(`DD_ADMIN_LANGFUSE_URL`), are linked and not asked. Traces are not exported to a viewer
([Transport](../../specs/transport.md)), so there is no link to one.

### Policy

The policy page reads `profile.yaml` with the harness's own parser, so it shows what the harness
enforces, and a profile the harness would refuse is reported with the harness's reason and not
shown. It compares the agents the profile allows with those in `agents.yaml` and flags each
mismatch: an agent the roster has and the profile does not allow, which the harness refuses, and
one the profile allows that nothing answers for. It lists what `deployment.yaml` turns off, and
says when the running app holds another profile version than the file, which is the case after
`apply` until the restart. People appear by identifier, as the People page shows them. Each
section names the `deployment.yaml` key that changes it; the page changes nothing.

### Escalations

The page shows each steward team's queue, for the teams the profile names: the escalations still
live in its projects (open, taken or waiting), the project each is in, who has taken it, and how
long it has been with the team. An open escalation is overdue once it has been with its team
longer than the profile's `stewardship.reroute_after`, which is when the sweep
(`data-director-escalations.timer`, on Operations) should send it again; one that stays overdue
means the sweep is not running. It shows no researcher's note and no steward's reply, and stewards
act in the app, not here. An escalation routed to a team the profile no longer names is not shown.

### Security

The page lists the security events ([Security](../../specs/security.md)): sign-ins and refusals,
sessions ended, steward actions, grants and enrolments, case downloads. Each service writes a
record to the journal; the page reads the deployment's units' journal for the last day or week
and keeps the lines that are records, newest first, by event, outcome and service. A record holds
a reason code and identifiers, never a message, a note or a secret, and the page keeps only the
fields a record is defined to carry, each cut short. Any process that logs to a unit can write a
line that looks like a record, so treat the page as what the services recorded, not as proof.
It needs `DD_ADMIN_SYSTEMD` to read the journal. A busy week's journal is large: the page asks
`journalctl` to search for the records and says if it could not, and it keeps the newest 1,000.

### Downloading a case

A run's page, a project's page and the runs page filtered to one conversation each end with
**Download case**: a zip of everything recorded about it, which a developer checks with
`dd-harness case verify` and opens with any reader of the stores, as
[Case files](../../specs/casefile.md) describes. It is the same case `dd-harness case export`
writes on the VM. Two options:

- **Name content by digest**, for a case that must leave the institution: every message, prompt,
  answer and draft is written as its digest; identifiers, times, outcomes, reason codes and titles
  are kept, and the project's files are left out.
- **Include the journal lines that name it**, from the deployment's units around the case's time,
  when the service reads journals (`DD_ADMIN_SYSTEMD`).

A case holds research content and personal data. Hand it to the developer privately, never in a
public issue, which names only the case's scope, identifier and `case.json` digest (`case verify`
prints it). Each download is recorded as a `case.exported` security event in the service's
journal, naming the admin service, since the service has no sign-in. The case is built in the
service's private `/tmp` and removed once sent.

### Secrets

No secret is kept in a settings file, and the doctor reports one that is. The configuration page
hides the value of any setting whose name contains `KEY`, `SECRET`, `TOKEN`, `PASSWORD`,
`PASSWD` or `CREDENTIAL`, unless the name ends in `_FILE`, which names where a secret is kept
rather than the secret. It cannot read `/etc/data-director/credentials/`, which is root's alone.

## Running it

`install.sh` installs and starts `data-director-admin.service` with the other units; it needs no
setting. On a VM installed before the service existed, run the installer once more from your
clone after the release that adds it is deployed (until then `data-director doctor` reports the
unit as not installed):

```bash
sudo deploy/install.sh --domain data-director.example.ac.uk
```

It restarts with the app on each deployment. Unlike the app, it does not wait for the agents, so it
answers when they are down.

```bash
systemctl status data-director-admin
journalctl -u data-director-admin -f
sudo systemctl restart data-director-admin
```

It writes nothing but a case it is sending, in its private `/tmp`. Its unit leaves every directory
read-only to it (`ProtectSystem=strict` with no `ReadWritePaths`), and it is in the `systemd-journal` group only to read the deployment's logs.

### Settings

The unit sets each of these; put an override in `/etc/data-director/admin.env`, which is
optional. It also reads `/etc/data-director/app.env`, for a `postgresql://` store and its `PG*`
settings.

| Variable | What it names | On the VM |
|---|---|---|
| `DD_RUNS_DIR`, `DD_PROJECTS_DIR` | The app's run and project stores | As the app's unit names them |
| `DD_AGENTS_CONFIG` | The `agents.yaml` the app reads | The live release's |
| `DD_ADMIN_APP_URL` | The app, for `/api/about` | `http://127.0.0.1:7860` |
| `DD_ADMIN_DOCTOR` | The command that prints the doctor's report as JSON | The live release's `scripts/dd.py --target vm doctor --json` |
| `DD_ADMIN_DEPLOY_ROOT` | The releases, `current` and `failed-commits` | `/opt/data-director` |
| `DD_ADMIN_ETC` | The settings the configuration page shows | `/etc/data-director` |
| `DD_ADMIN_SYSTEMD` | `yes` to read units' states and journals | `yes` |
| `DD_FEEDBACK_REPO` | Where the app files feedback | From `app.env`, else `data-director-agent/data-director` |
| `DD_ADMIN_LITELLM_URL` | The LLM gateway, for spend and prices | Unset; `http://127.0.0.1:4000` where the gateway runs |
| `DD_ADMIN_LITELLM_KEY_FILE` | A read-only gateway key | Unset: the `litellm-key` credential the unit's drop-in loads |
| `DD_ADMIN_MONTHLY_BUDGET` | A month's budget, in US dollars; shown, not enforced | Unset |
| `DD_ADMIN_BROKER_URL` | The model broker, for its health and summary | Set to `http://127.0.0.1:8300` by `broker-admin-credential.sh` |
| `DD_ADMIN_BROKER_KEY_FILE` | The operators' credential for the broker's summary | Unset: the `model-broker-admin` credential the drop-in loads |
| `DD_ADMIN_GRAFANA_URL`, `DD_ADMIN_PROMETHEUS_URL`, `DD_ADMIN_ALERTMANAGER_URL` | Each service, as your browser reaches it, for its link; the page also asks it from the VM. An `http` or `https` address with no user name | Unset: linked at `localhost:3000`, `9090` and `9093`, and not asked. To have the page ask, set them in `admin.env` (the monitoring profile's services are at `http://127.0.0.1:3000`, `:9090` and `:9093` on the VM) |
| `DD_ADMIN_LANGFUSE_URL` | Langfuse, if the gateway sends it traces | Unset: not linked |

A page whose setting is unset says which one, so the service also runs on a developer's machine:

```bash
DD_RUNS_DIR=/path/to/runs DD_PROJECTS_DIR=/path/to/projects \
DD_AGENTS_CONFIG=app/config/agents.yaml uv run dd-admin serve
```

## Limits of the alpha

- It reads the whole of both stores, once a minute at most. That suits an alpha's stores; a large
  deployment keeps them in PostgreSQL, where the listings could page from its index instead.
- It cannot change anything: deploying, restarting, rolling back and `apply` stay on the command
  line, with the commands on each page.
- It shows an agent's card as facts and JSON, not as the app draws it.
- It reads at most 1,000 of the gateway's keys and of its users, and says so past that.
- The gateway answers at most 10,000 calls for a window; past that the page says its spend is
  short. Costs are at the gateway's list prices, which can differ from what a provider bills.
