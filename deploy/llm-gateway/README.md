# LLM gateway: token and spend management

A ready-to-run [LiteLLM Proxy](https://docs.litellm.ai/) set-up that puts one endpoint in front of Anthropic, OpenAI, Gemini and local Ollama models. It records tokens and cost for every call, enforces budgets per key, user and team, and produces spend reports. It is optional: the app and agents run without it. Background, and the comparison with other tools, is in [background.md](background.md).

Tested on 11 November 2026 with LiteLLM `v1.109.0`, Postgres 16, Prometheus 3.5 and Grafana 12.1 (see [What was tested](#what-was-tested)).

```
deploy/llm-gateway/
├── compose.yaml              gateway + Postgres (+ Prometheus/Grafana with --profile monitoring)
├── compose.test.yaml         test overlay: fake provider, no real keys needed
├── config.yaml               models (Claude, OpenAI, Gemini, Ollama)
├── background.md             why LiteLLM, and how it compares with other tools
├── config.test.yaml          fake models used by the smoke test
├── .env.example              copy to .env and fill in
├── monitoring/prometheus.yml
└── scripts/
    ├── admin.py              teams, users, keys, spend reports, CSV export (stdlib only)
    ├── smoke_test.sh         end-to-end test of tracking, tags, budgets and metrics
    └── testing/fake_upstream.py
```

## Quick start

Requirements: Docker with Compose v2+, and Python 3.9+ for `admin.py`.

1. Create `.env` with fresh secrets:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env`. Generate each `sk-` secret with `echo "sk-$(openssl rand -hex 32)"` and add the provider keys you have.

2. Edit `config.yaml` and replace the `REPLACE-WITH-…` model IDs for OpenAI and Gemini. Delete any providers you don't use.

3. Start the gateway:
   ```bash
   docker compose up -d
   ```

4. Check it's running:
   ```bash
   curl http://localhost:4000/health/liveliness
   ```

5. Open the admin UI at <http://localhost:4000/ui>. Log in as `admin`, with your `LITELLM_MASTER_KEY` as the password.

Point code at the gateway with a **virtual key**, never a provider key. Using the OpenAI SDK (works for every model in `config.yaml`):

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:4000", api_key="sk-<virtual key>")
client.chat.completions.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"metadata": {"tags": ["experiment:ablation-2"]}},  # optional per-request tags
)
```

Using the Anthropic SDK (`/v1/messages`):

```python
import anthropic

client = anthropic.Anthropic(base_url="http://localhost:4000", api_key="sk-<virtual key>")
client.messages.create(
    model="claude-sonnet-5-5", max_tokens=1024, messages=[{"role": "user", "content": "Hello"}]
)
```

For existing code, setting `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` and the API key environment variables is often enough.

## Using it with Data Director agents

The agents create their Anthropic client with only an API key (`dd_sdk.credentials`), so the
Anthropic SDK takes its base URL from `ANTHROPIC_BASE_URL`. An agent moves to the gateway with no
code change:

1. Create a gateway key for the agent, so its spend is reported and limited on its own:
   ```bash
   scripts/admin.py key create advisor-standards --team <team_id> --budget 20 --period 30d \
       --models claude-sonnet-5-5 --tags agent:advisor-standards
   ```
2. On the VM, give the agent that key in place of the provider key (it arrives as
   `ANTHROPIC_API_KEY_FILE`, as before; [deploy/README.md](../README.md), "Secrets"):
   ```bash
   sudo data-director secret set advisor-standards anthropic-api-key   # paste the gateway key
   ```
3. Point the agent at the gateway in its local environment file, then restart it:
   ```bash
   echo 'ANTHROPIC_BASE_URL=http://127.0.0.1:4000' | sudo tee -a /etc/data-director/agents/advisor-standards.env
   ```

The provider key then lives only in the gateway's `.env`. This gives each agent a spending limit
of its own; without the gateway, limits are set per provider workspace
([Policy and identity](../../docs/specs/policy-and-identity.md), "Key hygiene"). The gateway listens
on 127.0.0.1:4000, which is clear of the app (7860), the workbench (8000) and the agents
(8101–8117).

## Day-to-day admin

`scripts/admin.py` reads `LITELLM_MASTER_KEY` from `.env`, and `LITELLM_URL` (default `http://localhost:4000`) from the environment.

Create a team for a group or grant, with a monthly budget:

```bash
scripts/admin.py team create nlp-lab --budget 200 --period 30d
```

Create a user in that team (prints a `user_id`):

```bash
scripts/admin.py user create someone@example.ac.uk --team <team_id> --budget 50 --period 30d
```

Create a key for one project; the tags are added to every request made with it:

```bash
scripts/admin.py key create thesis-ch3 --team <team_id> --user <user_id> \
    --budget 25 --period 30d --models claude-sonnet-5-5,gemini --tags project:thesis,grant:EP-X-1
```

Check spend against budget for a key, a team, or all teams:

```bash
scripts/admin.py key info sk-...
```

```bash
scripts/admin.py team info <team_id>
```

```bash
scripts/admin.py team list
```

See this month's spend grouped by team, or by tag, user, key, model or day:

```bash
scripts/admin.py spend --by team
```

See spend by tag for a date range:

```bash
scripts/admin.py spend --by tag --start 2026-10-01 --end 2026-10-31
```

Export the request logs to CSV:

```bash
scripts/admin.py export --start 2026-10-01 --end 2026-10-31 --out oct.csv
```

**Attribution tips**
- One key per project or grant, inside a team per group, gives clean attribution and enforceable budgets on the free tier.
- Tags give finer slicing (experiments, tasks) for reporting. `admin.py spend --by tag` aggregates them from the request logs, so you don't need the Enterprise-only `/global/spend/report`. A request with several tags counts towards each one.
- Don't rely on the OpenAI `user` field for accountability, because callers can set it to anything. Attach `--user` to the key instead.

## How budgets behave (tested)

- Before each request, the gateway checks the spend already recorded against every budget that applies (key, user, team). If any is used up, the request gets an error with `"type": "budget_exceeded"` (HTTP 422 in this version), naming the key or team.
- **The request that crosses a limit is still allowed.** Budgets can therefore be exceeded by about one request's cost, or by more if several requests are in flight at once. Leave some headroom, and set `max_tokens` on requests to bound the cost of each one.
- Budgets with `--period` reset automatically (e.g. `30d`).
- Spend reaches the database in batches, so `key info` and `team info` can lag by up to about a minute. Enforcement uses the live in-memory figure.

## Monitoring (optional)

Create a read-only key for Prometheus. This writes `monitoring/litellm_key`, which is git-ignored and world-readable so the Prometheus container can read it:

```bash
scripts/admin.py metrics-key
```

Then start the monitoring stack:

```bash
docker compose --profile monitoring up -d
```

- Prometheus is at <http://localhost:9090>. Useful queries: `sum by (team_alias) (litellm_spend_metric_total)`, `litellm_remaining_team_budget_metric` and `litellm_remaining_api_key_budget_metric`.
- Grafana is at <http://localhost:3000> (first login `admin`/`admin`). Add Prometheus as a data source with URL `http://prometheus:9090`.
- Budget gauges for every team and key are refreshed every 5 minutes (`prometheus_initialize_budget_metrics` in `config.yaml`).
- For alerts such as "team at 80% of budget", use Prometheus Alertmanager or Grafana alerting. LiteLLM's own email alerts are an Enterprise feature.

## Optional: Langfuse tracing

Run Langfuse yourself using [its Docker Compose guide](https://langfuse.com/self-hosting), or use Langfuse Cloud. Set `LANGFUSE_*` in `.env`, uncomment `success_callback: ["langfuse"]` in `config.yaml`, then:

```bash
docker compose up -d
```

## Testing without provider keys

Start the test stack. It uses `config.test.yaml` and a fake provider, so nothing is billed:

```bash
docker compose -f compose.yaml -f compose.test.yaml up -d
```

Run the test:

```bash
scripts/smoke_test.sh
```

Tear it down; `-v` deletes the test database:

```bash
docker compose -f compose.yaml -f compose.test.yaml down -v
```

### What was tested

`smoke_test.sh` passed 19/19 checks (on a fresh database and on a repeat run):
- the gateway, admin UI, team, user and key creation;
- calls through both the OpenAI (`/v1/chat/completions`) and Anthropic (`/v1/messages`) routes, costed correctly;
- the key budget and the team budget, both blocking further calls (spend stopped within one request of each limit);
- spend persisted per key and per team;
- tag totals for key-level and per-request tags;
- CSV export;
- Prometheus spend metrics.

Separately confirmed:
- an Anthropic SDK client built the way the agents build it (`anthropic.Anthropic(api_key=...)`),
  with only `ANTHROPIC_BASE_URL` set, reaches `claude-sonnet-5-5` through the gateway. Its spend is
  attributed to the key's tag, and a model outside the key's allow-list is refused (HTTP 403);
- the real `config.yaml` loads all five models;
- Prometheus scrapes the gateway with the read-only key;
- Grafana starts.

**Not tested here:** real provider calls (no API keys were available), Ollama, Langfuse, and running behind a reverse proxy.

LiteLLM's built-in `mock_response` option records **$0 cost** on the Anthropic route, which is why the test uses a fake provider instead.

## Production notes

- **Exposure:** ports are bound to `127.0.0.1`. To share the gateway with colleagues, put it behind an HTTPS reverse proxy (e.g. Caddy or nginx) on a campus network or VPN. Don't expose port 4000 directly.
- **Secrets:** keep `LITELLM_SALT_KEY` stable and backed up. Changing it makes the provider keys stored in the database unreadable.
- **Back-ups:** back up the `pgdata` volume, which holds keys, budgets and spend history. For example:
  ```bash
  docker compose exec db pg_dump -U litellm litellm > backup.sql
  ```
- **Privacy:** `turn_off_message_logging: true` keeps prompt and response text out of the spend logs. Decide on log retention in line with GDPR and any ethics approvals.
- **Prices:** LiteLLM costs requests using its built-in price list. At start-up it also tries to download the latest list from GitHub, and falls back to the built-in copy if that fails. Set `LITELLM_LOCAL_MODEL_COST_MAP=True` in `.env` to always use the version shipped with the image. For new or negotiated prices, set `input_cost_per_token` / `output_cost_per_token` under `model_info` in `config.yaml`.
- **Reconciliation:** the gateway's figures are estimates. Check them monthly against each provider's own usage and cost reports (see the guide). Giving the gateway its own provider keys or workspace makes this one-to-one.
- **Large exports:** `/spend/logs/v2` returns at most 10,000 rows per query, so use shorter date ranges, or query Postgres directly (table `"LiteLLM_SpendLogs"`).
- **Upgrades:** the image is pinned to `v1.109.0`. Read the release notes before bumping it, then re-run the smoke test.
