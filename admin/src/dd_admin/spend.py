"""What the deployment spends on language models (docs/guide/operations/admin.md, "Spend").

Two sources, kept apart on the page:

- **The gateway** (`deploy/llm-gateway/`), when the agents call models through it: what each call
  cost, as LiteLLM priced it, from its spend logs. This is the actual figure, by day, model and
  gateway key (one key per agent).
- **The run store**: the tokens each run's agent reported, by model (`telemetry.model_calls`),
  priced at the gateway's own per-token prices (`/model/info`). This is an estimate, but it is the
  only one that can say which person or project a call was for.

Tokens on a model the gateway does not price are counted as unpriced, never as costing nothing.
Nothing here writes: the gateway key needs only the `proxy_admin_viewer` role.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_admin.usage import DAYS_CHARTED, Usage

PAGE_SIZE = 1000
# The spend log API returns at most this many rows for a window; past it the totals are short.
MAX_PAGES = 10
WARN_SHARE = 0.8


@dataclass(frozen=True)
class Price:
    """What one token costs, in the gateway's currency."""

    input: float
    output: float


@dataclass(frozen=True)
class Prices:
    """The gateway's prices, by the names a run's `model_id` may carry."""

    by_name: dict[str, Price] = field(default_factory=dict)

    @classmethod
    def from_model_info(cls, doc: object) -> Prices:
        """Read `/model/info`. A model without both prices is left out, so its tokens are
        unpriced rather than free; a price of 0 (a local model) is a price."""
        found: dict[str, Price] = {}
        rows = doc.get("data") if isinstance(doc, dict) else None
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            info = row.get("model_info") or {}
            cost_in, cost_out = info.get("input_cost_per_token"), info.get("output_cost_per_token")
            if not (isinstance(cost_in, int | float) and isinstance(cost_out, int | float)):
                continue
            if not (_is_number(cost_in) and _is_number(cost_out)):
                continue
            price = Price(float(cost_in), float(cost_out))
            upstream = str((row.get("litellm_params") or {}).get("model") or "")
            for name in (row.get("model_name"), upstream, upstream.rsplit("/", 1)[-1]):
                if isinstance(name, str) and name:
                    found.setdefault(name, price)
        return cls(found)

    def lookup(self, model_id: str) -> Price | None:
        """The price of `model_id`: by its name, or by the longest known name it extends with a
        dated or versioned suffix (`claude-sonnet-5-5-20261001`)."""
        if model_id in self.by_name:
            return self.by_name[model_id]
        bare = model_id.rsplit("/", 1)[-1]
        if bare in self.by_name:
            return self.by_name[bare]
        stems = [n for n in self.by_name if bare.startswith(n + "-") or bare.startswith(n + "@")]
        return self.by_name[max(stems, key=len)] if stems else None

    def __bool__(self) -> bool:
        return bool(self.by_name)


@dataclass
class Line:
    """Tokens and cost, summed over calls or runs."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    unpriced_tokens: int = 0

    def add(self, other: Line) -> None:
        self.requests += other.requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost += other.cost
        self.unpriced_tokens += other.unpriced_tokens


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0


def _ranked(lines: dict[str, Line]) -> list[tuple[str, Line]]:
    return sorted(
        lines.items(),
        key=lambda kv: (-kv[1].cost, -(kv[1].input_tokens + kv[1].output_tokens), kv[0]),
    )


# --- The gateway ---------------------------------------------------------------------------------


@dataclass
class GatewaySpend:
    """What the gateway's spend logs say, for this month and the last 30 days."""

    configured: bool = False
    error: str | None = None
    capped: bool = False
    prices: Prices = field(default_factory=Prices)
    month_start: date | None = None
    month_to_date: float = 0.0
    last_30_days: float = 0.0
    requests_30_days: int = 0
    per_day: list[tuple[str, float]] = field(default_factory=list)  # oldest first
    by_model: list[tuple[str, Line]] = field(default_factory=list)  # last 30 days
    by_key: list[tuple[str, Line]] = field(default_factory=list)  # last 30 days

    @property
    def answered(self) -> bool:
        return self.configured and self.error is None


def _key_of(row: dict[str, Any]) -> str:
    """Which gateway key made the call: its alias, else an `agent:` tag, else unknown. The key
    itself is never shown."""
    metadata = row.get("metadata") or {}
    alias = metadata.get("user_api_key_alias") if isinstance(metadata, dict) else None
    if isinstance(alias, str) and alias:
        return alias
    for tag in row.get("request_tags") or []:
        if isinstance(tag, str) and tag.startswith("agent:"):
            return tag
    return "(unknown key)"


def _started(row: dict[str, Any]) -> datetime | None:
    value = row.get("startTime")
    if not isinstance(value, str):
        return None
    try:
        found = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def summarise(
    rows: Iterable[dict[str, Any]], now: datetime, prices: Prices | None = None
) -> GatewaySpend:
    """Sum spend log rows into this month, the last 30 days, and the last 30 days by day, model
    and key."""
    found = GatewaySpend(configured=True, prices=prices or Prices())
    month_start = now.date().replace(day=1)
    found.month_start = month_start
    since = now - timedelta(days=DAYS_CHARTED)
    days = [(now - timedelta(days=n)).date() for n in range(DAYS_CHARTED - 1, -1, -1)]
    per_day: defaultdict[date, float] = defaultdict(float)
    by_model: dict[str, Line] = {}
    by_key: dict[str, Line] = {}
    for row in rows:
        at = _started(row)
        if at is None or at > now:
            continue
        cost = float(row["spend"]) if _is_number(row.get("spend")) else 0.0
        if at.date() >= month_start:
            found.month_to_date += cost
        if at < since:
            continue
        found.last_30_days += cost
        found.requests_30_days += 1
        per_day[at.date()] += cost
        line = Line(
            1,
            int(row.get("prompt_tokens") or 0),
            int(row.get("completion_tokens") or 0),
            cost,
        )
        model = str(row.get("model_group") or row.get("model") or "(unknown model)")
        by_model.setdefault(model, Line()).add(line)
        by_key.setdefault(_key_of(row), Line()).add(line)
    found.per_day = [(day.isoformat(), per_day.get(day, 0.0)) for day in days]
    found.by_model = _ranked(by_model)
    found.by_key = _ranked(by_key)
    return found


def read_gateway(
    settings: AdminSettings, system: System, now: datetime | None = None
) -> GatewaySpend:
    """Ask the gateway for its prices and its spend logs since the earlier of the first of the
    month and 30 days ago. A gateway that does not answer is named in `error`, so the page still
    shows what the run store holds."""
    now = now or datetime.now(UTC)
    if not settings.litellm_url:
        return GatewaySpend()
    base = settings.litellm_url.rstrip("/")
    if settings.litellm_key_file is None:
        return GatewaySpend(
            configured=True,
            error=(
                "no gateway key: set DD_ADMIN_LITELLM_KEY_FILE or load the litellm-key credential"
            ),
        )
    key = (system.read_text(settings.litellm_key_file) or "").strip()
    if not key:
        return GatewaySpend(
            configured=True, error=f"the gateway key at {settings.litellm_key_file} cannot be read"
        )
    headers = {"Authorization": f"Bearer {key}"}

    prices = Prices.from_model_info(system.get_json(f"{base}/model/info", headers))

    start = min(now.date().replace(day=1), (now - timedelta(days=DAYS_CHARTED)).date())
    window = {"start_date": f"{start} 00:00:00", "end_date": f"{now.date()} 23:59:59"}
    rows: list[dict[str, Any]] = []
    capped = False
    page = 1
    while True:
        query = urlencode({**window, "page": page, "page_size": PAGE_SIZE})
        doc = system.get_json(f"{base}/spend/logs/v2?{query}", headers)
        if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
            return GatewaySpend(
                configured=True,
                prices=prices,
                error=f"the gateway at {base} did not return its spend logs",
            )
        rows.extend(r for r in doc["data"] if isinstance(r, dict))
        capped = capped or bool(doc.get("total_is_capped"))
        total_pages = doc.get("total_pages")
        if not isinstance(total_pages, int) or page >= total_pages:
            break
        if page >= MAX_PAGES:
            capped = True
            break
        page += 1
    found = summarise(rows, now, prices)
    found.capped = capped
    return found


# --- Estimates from the run store ----------------------------------------------------------------


def cost_of(calls: Iterable[tuple[str, int, int]], prices: Prices) -> Line:
    """Tokens and estimated cost of a run's calls, as `(model_id, in, out)`."""
    line = Line()
    for model_id, tokens_in, tokens_out in calls:
        line.requests += 1
        line.input_tokens += tokens_in
        line.output_tokens += tokens_out
        price = prices.lookup(model_id)
        if price is None:
            line.unpriced_tokens += tokens_in + tokens_out
        else:
            line.cost += tokens_in * price.input + tokens_out * price.output
    return line


def cost_of_runs(runs: Iterable[dict[str, Any]], prices: Prices) -> Line:
    """The summed estimate over `runs` (rows from `dd_admin.usage.run_row`)."""
    total = Line()
    for run in runs:
        total.add(cost_of(run["calls"], prices))
    return total


@dataclass
class Estimate:
    """The run store's tokens over the last 30 days, priced at the gateway's prices, by model,
    agent, person and project."""

    priced: bool
    total: Line
    by_model: list[tuple[str, Line]]
    by_agent: list[tuple[str, Line]]
    by_person: list[tuple[str, str, Line]]  # principal_id, name, line
    by_project: list[tuple[str, str, Line]]  # project_id, title, line


def estimate(found: Usage, prices: Prices, days: int = DAYS_CHARTED) -> Estimate:
    since = found.made_at - timedelta(days=days)
    total = Line()
    by_model: dict[str, Line] = {}
    by_agent: dict[str, Line] = {}
    by_person: dict[str, Line] = {}
    by_project: dict[str, Line] = {}
    for run in found.runs:
        if run["at"] is None or run["at"] < since or not run["calls"]:
            continue
        line = cost_of(run["calls"], prices)
        total.add(line)
        for model_id, tokens_in, tokens_out in run["calls"]:
            by_model.setdefault(model_id, Line()).add(
                cost_of([(model_id, tokens_in, tokens_out)], prices)
            )
        by_agent.setdefault(run["agent_id"] or "unknown", Line()).add(line)
        if run["principal_id"]:
            by_person.setdefault(run["principal_id"], Line()).add(line)
        if run["project_id"]:
            by_project.setdefault(run["project_id"], Line()).add(line)
    names = {p.principal_id: p.name for p in found.people}
    titles = {p.get("project_id"): p.get("title") for p in found.projects}
    return Estimate(
        priced=bool(prices),
        total=total,
        by_model=_ranked(by_model),
        by_agent=_ranked(by_agent),
        by_person=[(k, names.get(k, k), v) for k, v in _ranked(by_person)],
        by_project=[(k, titles.get(k) or "Untitled project", v) for k, v in _ranked(by_project)],
    )


# --- Budget --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Budget:
    """This month's spend against `DD_ADMIN_MONTHLY_BUDGET`. Shown, never enforced: limits that
    stop calls are the gateway's (keys, users and teams)."""

    limit: float | None
    spent: float | None  # None when the gateway has not said

    @property
    def share(self) -> float | None:
        if self.limit is None or self.spent is None:
            return None
        return self.spent / self.limit

    @property
    def state(self) -> str:
        """`none` (no budget, or no figure to compare), `good`, `warn` (80 % or more) or
        `over`."""
        share = self.share
        if share is None:
            return "none"
        if share >= 1:
            return "over"
        return "warn" if share >= WARN_SHARE else "good"
