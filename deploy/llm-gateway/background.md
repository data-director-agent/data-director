# LLM token and spend management: an off-the-shelf approach

*Checked against vendor documentation in November 2026, and the set-up below was tested end-to-end with LiteLLM v1.109.0. Config keys and endpoints change often, so pin versions and re-check before relying on them.*

> **Ready-to-run version:** this directory contains the tested Compose files, configuration, an admin CLI (`scripts/admin.py`) and a smoke test. Section 3 below explains the pieces; the [README](README.md) is the practical reference.

## TL;DR

1. **Run a self-hosted [LiteLLM Proxy](https://docs.litellm.ai/) with Postgres** as a single gateway in front of Anthropic, OpenAI, Gemini and local models (Ollama). Every call is metered, costed and attributed to a key, user and team.
2. **Use virtual keys plus team budgets** for limits and multi-user sharing. Give each person, project or grant its own key or team, with a `max_budget` and a `budget_duration`. This is all in the free, open-source edition.
3. **Optionally add [Langfuse](https://langfuse.com/)** (self-hosted) for per-request traces, and Prometheus/Grafana for dashboards. Reconcile against each provider's own billing every month.

---

## 1. Comparison of options

| Tool | Type | Self-host | Anthropic / OpenAI / Gemini / Ollama | Budget enforcement | Tags / attribution | Dashboard | Multi-user | Licence / cost | Status (Nov 2026) |
|---|---|---|---|---|---|---|---|---|---|
| **LiteLLM Proxy** | Gateway (proxy) | Yes (Docker + Postgres) | Yes, all | **Yes**: per key, user and team, with resets (OSS). Tag and per-model budgets are Enterprise | Request tags and spend-log metadata; team or key attribution | Admin UI at `/ui`, Prometheus | Yes (users, teams, orgs). SSO free for up to 5 users | MIT core; Enterprise licence for extras | Active |
| **Langfuse** | Tracing / observability (SDK or callback) | Yes (MIT) | Via SDK integrations or LiteLLM callback | No: it reports, it doesn't block | Rich (trace metadata, users, sessions) | Yes, very good | Yes | MIT self-host; paid cloud and Enterprise | Active |
| **Portkey** | Gateway (hosted, with an OSS gateway core) | Partly | Yes | Yes, mostly on paid tiers | Yes | Yes | Yes | Freemium / commercial | Acquired by Palo Alto Networks (closed around May 2026), now part of Prisma AIRS; roadmap leaning towards enterprise security |
| **Helicone** | Logging proxy | Was possible | Yes | Limited | Yes | Yes | Yes | Was OSS | **Maintenance mode** since its acquisition by Mintlify (March 2026): no new features, so avoid for new set-ups |
| **OpenRouter** | Hosted router / reseller | No | Yes (one bill) | Per-key credit limits | Basic | Basic | Basic | Pay-as-you-go plus a margin | Active. Prompts go through a third party |
| **Provider consoles** (Anthropic Console, OpenAI dashboard, Google Cloud Billing) | Native billing | n/a | One provider each | Workspace or project limits only | By API key / workspace / project | Yes | Yes | Free | Authoritative figures, but siloed per provider |

**Why LiteLLM wins on your criteria:** it is the only option here that is free, self-hosted, covers all four provider types, *enforces* budgets (rather than just reporting them) and handles multiple users and teams. Self-hosting also means prompts and logs stay on infrastructure you control, which helps with university data-protection and ethics requirements.

---

## 2. Architecture

```
  scripts / notebooks / apps / colleagues
        │   (OpenAI- or Anthropic-compatible SDKs, virtual key per person/project)
        ▼
 ┌─────────────────────────────┐        ┌──────────────────────┐
 │  LiteLLM Proxy  :4000       │──────▶ │ Postgres             │  keys, teams, budgets, spend logs
 │  - auth (virtual keys)      │        └──────────────────────┘
 │  - budget / rate checks     │──────▶  Prometheus /metrics ──▶ Grafana (optional)
 │  - cost calculation         │──────▶  Langfuse callback      (optional traces)
 └─────────────┬───────────────┘
               ▼
  Anthropic · OpenAI · Gemini · Ollama (local)
```

Before forwarding a request, the proxy checks the spend already recorded against the key's, user's and team's budgets. In testing, **the request that crosses a limit was still allowed, and every later request was refused** until the budget reset. So a budget can be exceeded by about one request's cost, or more with concurrent requests. Leave headroom, and set `max_tokens` to bound the cost of each request.

---

## 3. Set-up walkthrough

### 3.1 Files

`.env` (never commit this):

```bash
# Generate each with: openssl rand -hex 32  (LiteLLM keys must start with sk-)
LITELLM_MASTER_KEY=sk-<long-random>
LITELLM_SALT_KEY=sk-<long-random>     # encrypts provider creds in the DB; do NOT change after adding models
POSTGRES_PASSWORD=<long-random>

ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...

# Optional, for Langfuse
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=http://langfuse:3000
```

`compose.yaml` (abridged here; the full, tested file is in this directory):

```yaml
services:
  litellm:
    image: ghcr.io/berriai/litellm:v1.109.0   # pinned; tested November 2026
    ports: ["4000:4000"]
    env_file: .env
    environment:
      DATABASE_URL: postgresql://litellm:${POSTGRES_PASSWORD}@db:5432/litellm
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    depends_on: [db]
    restart: unless-stopped

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: litellm
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: litellm
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  pgdata:
```

`config.yaml`:

```yaml
model_list:
  # Anthropic
  - model_name: claude-sonnet-5-5
    litellm_params:
      model: anthropic/claude-sonnet-5-5
      api_key: os.environ/ANTHROPIC_API_KEY

  # OpenAI: substitute a current model ID
  - model_name: gpt
    litellm_params:
      model: openai/<openai-model-id>
      api_key: os.environ/OPENAI_API_KEY

  # Google Gemini (AI Studio key); use vertex_ai/ for Vertex
  - model_name: gemini
    litellm_params:
      model: gemini/<gemini-model-id>
      api_key: os.environ/GEMINI_API_KEY

  # Local Ollama: free, but still metered for tokens
  - model_name: llama-local
    litellm_params:
      model: ollama_chat/llama3.1
      api_base: os.environ/OLLAMA_API_BASE   # e.g. http://host.docker.internal:11434
    model_info:
      input_cost_per_token: 0
      output_cost_per_token: 0

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL

litellm_settings:
  callbacks: ["prometheus"]          # /metrics (OSS; needs an admin or admin-viewer key to read)
  # success_callback: ["langfuse"]   # uncomment if running Langfuse
```

Start it:

```bash
docker compose up -d
```

The admin UI is at `http://localhost:4000/ui`. Log in as `admin`, with your `LITELLM_MASTER_KEY` as the password.

> **Pricing:** LiteLLM ships a model cost map, so known models are costed automatically. For anything it doesn't know (new models, local or self-hosted ones, negotiated rates), set `input_cost_per_token` / `output_cost_per_token` in `model_info`, or set both to `0` to mark the model as free. A warning in the logs (`pricing entry ... has no input_cost_per_token`) tells you when a rate is missing.

### 3.2 Teams, users and keys with budgets

Create a team, e.g. a research group or grant, with a monthly cap:

```bash
curl -s http://localhost:4000/team/new \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"team_alias": "nlp-lab", "max_budget": 200, "budget_duration": "30d"}'
```

Create a user:

```bash
curl -s http://localhost:4000/user/new \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"user_email": "someone@example.ac.uk", "max_budget": 50, "budget_duration": "30d"}'
```

Issue a key for a specific project, with its own budget, rate limits and model allow-list:

```bash
curl -s http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{
        "team_id": "<team_id from above>",
        "user_id": "<user_id from above>",
        "models": ["claude-sonnet-5-5", "gemini", "llama-local"],
        "max_budget": 25, "budget_duration": "30d",
        "tpm_limit": 200000, "rpm_limit": 60,
        "metadata": {"project": "thesis-ch3", "grant": "EP/XXXX/1"}
      }'
```

Budgets stack: a call is refused if the key's, user's or team's budget is used up. Keys and teams can also be managed from the admin UI, or with `scripts/admin.py` in the ready-to-run folder.

### 3.3 Attribution (tags)

- **Free and reliable:** one key per project, grant or experiment (as above). Spend is then filterable by `api_key`, `user_id` or `team_id`.
- **Per-request tags:** add tags to an individual call:
  ```json
  "metadata": {"tags": ["project:thesis-ch3", "experiment:ablation-2"]}
  ```
  You can also send a header: `x-litellm-spend-logs-metadata: {"project_id": "thesis-ch3"}`.
- **Caveat:** *tag-based budgets* and *spend reports grouped by tag* are LiteLLM **Enterprise** features. Tags are still stored in the spend logs (field `request_tags`, which merges key-level and per-request tags), so you can aggregate them yourself: `scripts/admin.py spend --by tag` does exactly that. To enforce budgets for free, use teams or keys.
- Don't rely on the OpenAI `user` field for accountability, because callers can set it to anything. Bind `user_id` to the key instead.

### 3.4 Client usage

Use the OpenAI SDK for any model behind the proxy:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:4000", api_key="sk-<virtual-key>")
r = client.chat.completions.create(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"metadata": {"tags": ["project:thesis-ch3"]}},
)
```

The Anthropic SDK works too, via the proxy's `/v1/messages` route, and spend is still tracked:

```python
import anthropic

client = anthropic.Anthropic(base_url="http://localhost:4000", api_key="sk-<virtual-key>")
client.messages.create(
    model="claude-sonnet-5-5", max_tokens=256, messages=[{"role": "user", "content": "Hello"}]
)
```

Existing code usually only needs `base_url` and `api_key` changed, e.g. via `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` environment variables.

---

## 4. Reporting

| Need | How |
|---|---|
| Quick look | Admin UI (`/ui`): spend by key, team, user and model; usage charts |
| Raw per-request data | `GET /spend/logs?start_date=…&end_date=…&summarize=false` (capped at the most recent 10,000 rows) |
| Exports and filtering | `GET /spend/logs/v2?start_date=…&end_date=…&team_id=…&model=…&page=1&page_size=1000` |
| Per user | `GET /user/info?user_id=…`, `/user/daily/activity?start_date=…&end_date=…` |
| Grouped reports (`/global/spend/report`) | **Enterprise**. On the free tier, use `scripts/admin.py spend --by team` (or `tag`, `user`, `key`, `model`, `day`), which aggregates `/spend/logs/v2` |
| Live dashboards and alerts | Prometheus (`callbacks: ["prometheus"]`), e.g. `litellm_spend_metric_total` (a counter, so note the `_total` suffix), `litellm_remaining_team_budget_metric`, `litellm_remaining_api_key_budget_metric`. Scraping needs an admin or read-only `proxy_admin_viewer` key (`scripts/admin.py metrics-key`). Graph them in Grafana and use Alertmanager for "80% of budget used" alerts |
| Traces / debugging | Langfuse via `success_callback: ["langfuse"]` |

Soft-budget *email* alerts are an Enterprise feature. The free route to alerts is Prometheus + Alertmanager.

For example, to export a month's spend as CSV with `jq` (or simply `scripts/admin.py export --start … --end … --out file.csv`):

```bash
curl -s "http://localhost:4000/spend/logs/v2?start_date=2026-10-01%2000:00:00&end_date=2026-10-31%2023:59:59&page_size=1000" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
| jq -r '.data[] | [.startTime, .model, .api_key, .team_id, .prompt_tokens, .completion_tokens, .spend] | @csv'
```

(These field names were confirmed against v1.109.0. Team and key aliases are under `metadata.user_api_key_team_alias` and `metadata.user_api_key_alias`.)

---

## 5. Reconciling with provider billing

Gateway costs are **estimates** based on list prices and token counts. Caching discounts, batch pricing, priority tiers, taxes and credits can all make them diverge from what you're actually billed. Reconcile monthly:

- **Anthropic:** the Admin API's Usage and Cost endpoints (`/v1/organizations/usage_report/messages` and `/v1/organizations/cost_report`). These need an Admin API key, which requires an organisation account. Anthropic's docs now call these "legacy" and point new integrations to its Usage and Cost Analytics API.
- **OpenAI:** the organisation Usage and Costs API, or the usage dashboard.
- **Gemini:** Google Cloud Billing export to BigQuery (for Vertex or paid AI Studio projects).
- **Ollama:** no cost, so only token volumes matter, plus compute time if you want to charge for it.

It also helps to give the proxy **its own provider API keys** (or a dedicated workspace or project) at each provider. Provider-side reports then line up one-to-one with gateway traffic, and you can set a provider-side hard limit as a final backstop.

---

## 6. When to choose something else

- **You only want visibility, not enforcement:** Langfuse on its own, via SDK wrappers or OpenTelemetry. It's lighter to adopt for code that doesn't share a gateway.
- **You want zero infrastructure and one invoice:** OpenRouter, with per-key credit limits. The trade-off is that prompts go through a third party and you pay a margin, which may not be acceptable for research data.
- **One provider only:** that provider's console limits plus its usage API may be enough.
- **Institution-wide roll-out with SSO for more than 5 users, audit logs and tag budgets:** LiteLLM Enterprise, or a commercial gateway. Talk to your IT services about procurement and data processing agreements.

---

## 7. Operational notes

- Keep `LITELLM_SALT_KEY` stable and backed up. Changing it makes the provider credentials stored in the database unreadable.
- Back up the Postgres volume, since it holds the spend history.
- Put the proxy behind HTTPS (e.g. Caddy or nginx) and restrict access (VPN or campus network) before sharing it with colleagues.
- Spend logs may contain metadata, and, if enabled, prompt content. Decide on retention in line with GDPR and your ethics approvals.
- Pin the image tag and read the release notes before upgrading; the project moves quickly.

---

## Sources

- Testing: `scripts/smoke_test.sh` (19/19 checks passed against LiteLLM v1.109.0, 11 November 2026)
- LiteLLM: [Virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys) · [Spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking) · [Tag budgets](https://docs.litellm.ai/docs/proxy/tag_budgets) · [Enterprise features](https://docs.litellm.ai/docs/enterprise) · [Prometheus](https://docs.litellm.ai/docs/proxy/prometheus) · [Docker quick start](https://docs.litellm.ai/docs/proxy/docker_quick_start) · [Production deploy](https://docs.litellm.ai/docs/proxy/deploy) · [Logging / Langfuse](https://docs.litellm.ai/docs/proxy/logging) · [Anthropic `/v1/messages`](https://docs.litellm.ai/docs/anthropic_unified) · [Ollama](https://docs.litellm.ai/docs/providers/ollama)
- Anthropic: [Usage and Cost API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api)
- Helicone: [Mintlify acquires Helicone](https://mintlify.com/blog/mintlify-acquires-helicone) · [Helicone joins Mintlify](https://www.helicone.ai/blog/joining-mintlify)
- Portkey: [GovConWire – Palo Alto Networks acquires Portkey](https://www.govconwire.com/articles/palo-alto-networks-portkey-acquisition-prisma-airs) · [Nand Research analysis](https://nand-research.com/palo-alto-networks-portkey-acquisition-anchors-its-agentic-security-stack/)
- Comparisons (third-party, vendor-authored; treat with care): [FutureAGI – LLM cost tracking tools 2026](https://futureagi.com/blog/best-llm-cost-tracking-tools-2026/) · [Langfuse vs Helicone (DEV)](https://dev.to/bean_bean/langfuse-vs-helicone-i-tested-both-for-llm-observability-2026-1bnk)
