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
(`-L 9200:127.0.0.1:8200`, then <http://localhost:9200>).

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
| Overview | Health, the running commit, agents up, people active, runs and projects over 7 and 30 days, runs per day, outcomes, the latest runs | All of the below |
| Operations | Each problem `data-director doctor` finds, with its fix; its notes and what it skipped; the releases on disk, which is live and which failed to start; each unit's state, restarts and last 100 journal lines | `data-director doctor --json`, run as the service's user; `/opt/data-director`; `systemctl show`; `journalctl` |
| Agents | Each agent in `agents.yaml`: whether its card answers, its unit, version, action class and models; the card in full | Each agent's `/.well-known/agent-card.json` |
| People | Everyone a run acted for or who created a project: their runs, conversations and projects, and when they were first and last seen | The run and project stores |
| Runs | Every run, newest first, by agent, outcome, person, project or conversation; a run's outcome, who it acted for, telemetry, estimated cost and envelope | The run store |
| Spend | Spend this month against an optional budget; spend over the last 30 days by day, model and gateway key; the tokens runs recorded over 30 days by model, agent, person and project, with their estimated cost | The LLM gateway's `/spend/logs/v2` and `/model/info`; the run store |
| Projects | Every project: who created it, its documents and repository; a project's event log and runs | The project store |
| Configuration | The files under `/etc/data-director`, each with the command that changes it; the stores' locations and the live profile | `/etc/data-director`; the app's `/api/about` |
| Feedback | A link to the feedback issues | `DD_FEEDBACK_REPO` |

The stores and the doctor are read at most once a minute, and the gateway every five minutes;
**Refresh** reads them again.

### Spend

Spend comes from the optional LLM gateway ([deploy/llm-gateway](../../../deploy/llm-gateway/README.md)),
when the agents call their models through it. The page keeps two figures apart:

- **The gateway's**, which LiteLLM priced as each call was made: the month to date, the last
  30 days by day, by model and by gateway key (one key per agent).
- **An estimate from the runs**: the tokens each run's agent reported (`telemetry.model_calls`),
  priced at the gateway's own per-token prices. Only this one can say which person or project the
  tokens were for, so the person, project and run pages show it too. It differs from the
  gateway's figure when an agent calls a model without the gateway, when something else uses the
  gateway, and by discounts such as cached input. Tokens on a model the gateway has no price for
  are counted as unpriced, not as free.

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
them. Who may use the workbench is `DD_WORKBENCH_ADMINS` ([Configuration](configuration.md)).

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

It writes nothing. Its unit leaves every directory read-only to it (`ProtectSystem=strict` with no
`ReadWritePaths`), and it is in the `systemd-journal` group only to read the deployment's logs.

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
- The gateway answers at most 10,000 calls for a window; past that the page says its spend is
  short. Costs are at the gateway's list prices, which can differ from what a provider bills.
