"""The LLM gateway as its operators need to see it (docs/guide/operations/admin.md, "Gateway").

The Spend page says what the deployment's model calls cost; this page says how the gateway
(`deploy/llm-gateway/`, LiteLLM) is set up to allow and limit them:

- whether it is up and its database connected (`/health/readiness`);
- the models it serves, with their upstream, prices and limits (`/model/info`);
- its keys, teams and users, each with what it has spent against its budget, its period and
  when that resets, and its rate limits (`/key/list`, `/team/list`, `/user/list`).

A key is shown by its alias, never by the key or its hash. Nothing here writes: the gateway key
needs only the `proxy_admin_viewer` role, and every change is made with
`deploy/llm-gateway/scripts/admin.py`, which the page names.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from dd_admin.litellm import Gateway, connect
from dd_admin.settings import AdminSettings
from dd_admin.spend import Budget, Price, Prices
from dd_admin.system import System

PAGE_SIZE = 100
# Past this many pages of keys or users the page says it shows only some.
MAX_PAGES = 10


@dataclass(frozen=True)
class Model:
    """One model the gateway serves, by the name agents ask for."""

    name: str
    upstream: str
    provider: str
    price: Price | None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    rpm: int | None = None
    tpm: int | None = None


@dataclass(frozen=True)
class Allowance:
    """A key, team or user: what it has spent against its budget, and its limits."""

    name: str
    ident: str
    spend: float
    max_budget: float | None
    period: str | None = None
    resets: datetime | None = None
    models: tuple[str, ...] = ()
    rpm: int | None = None
    tpm: int | None = None
    team: str | None = None
    expires: datetime | None = None
    blocked: bool = False
    role: str | None = None

    @property
    def budget(self) -> Budget:
        return Budget(self.max_budget, self.spend)


@dataclass
class GatewayState:
    """What the gateway says about itself. `error` is set when it could not be asked at all;
    `problems` names each part that did not answer, so the rest still shows."""

    configured: bool = False
    error: str | None = None
    problems: list[str] = field(default_factory=list)
    ready: bool = False
    database: str | None = None
    version: str | None = None
    models: list[Model] = field(default_factory=list)
    keys: list[Allowance] = field(default_factory=list)
    teams: list[Allowance] = field(default_factory=list)
    users: list[Allowance] = field(default_factory=list)
    capped: list[str] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return self.configured and self.error is None


# --- Reading LiteLLM's documents -----------------------------------------------------------------


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return float(value)


def _int(value: object) -> int | None:
    found = _number(value)
    return int(found) if found is not None else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _when(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _models(value: object) -> tuple[str, ...]:
    return tuple(m for m in value if isinstance(m, str)) if isinstance(value, list) else ()


def models_from(doc: object) -> list[Model]:
    """`/model/info`, one entry per model name, sorted by name."""
    prices = Prices.from_model_info(doc)
    rows = doc.get("data") if isinstance(doc, dict) else None
    found: dict[str, Model] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _text(row.get("model_name")):
            continue
        info = _mapping(row.get("model_info"))
        params = _mapping(row.get("litellm_params"))
        upstream = str(params.get("model") or "")
        name = row["model_name"]
        found.setdefault(
            name,
            Model(
                name=name,
                upstream=upstream,
                provider=str(info.get("litellm_provider") or upstream.partition("/")[0] or "—"),
                price=prices.by_name.get(name),
                max_input_tokens=_int(info.get("max_input_tokens")),
                max_output_tokens=_int(info.get("max_output_tokens")),
                rpm=_int(params.get("rpm")),
                tpm=_int(params.get("tpm")),
            ),
        )
    return [found[name] for name in sorted(found)]


def allowance(row: dict[str, Any], name_keys: tuple[str, ...], ident_key: str) -> Allowance:
    """A key, team or user row. Its name is the first of `name_keys` it has; a key's token and
    hash are never read."""
    ident = str(row.get(ident_key) or "")
    name = next((row[k] for k in name_keys if _text(row.get(k))), None)
    return Allowance(
        name=name or "(no alias)",
        ident=ident,
        spend=_number(row.get("spend")) or 0.0,
        max_budget=_number(row.get("max_budget")),
        period=_text(row.get("budget_duration")),
        resets=_when(row.get("budget_reset_at")),
        models=_models(row.get("models")),
        rpm=_int(row.get("rpm_limit")),
        tpm=_int(row.get("tpm_limit")),
        team=_text(row.get("team_alias")) or _text(row.get("team_id")),
        expires=_when(row.get("expires")),
        blocked=row.get("blocked") is True,
        role=_text(row.get("user_role")),
    )


def _ranked(found: list[Allowance]) -> list[Allowance]:
    return sorted(found, key=lambda a: (-a.spend, a.name))


# --- Asking the gateway --------------------------------------------------------------------------


def _paged(
    system: System, gateway: Gateway, path: str, rows_key: str, size_key: str
) -> tuple[list[dict[str, Any]], bool] | None:
    """Every row of a paged list, and whether there were more than `MAX_PAGES` pages."""
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urlencode({"page": page, size_key: PAGE_SIZE, "return_full_object": "true"})
        doc = system.get_json(f"{gateway.base}{path}?{query}", gateway.headers)
        if not isinstance(doc, dict) or not isinstance(doc.get(rows_key), list):
            return None
        rows.extend(r for r in doc[rows_key] if isinstance(r, dict))
        total = doc.get("total_pages")
        if not isinstance(total, int) or page >= total:
            return rows, False
        if page >= MAX_PAGES:
            return rows, True
        page += 1


def _read_lists(system: System, gateway: Gateway, found: GatewayState) -> None:
    lists: list[tuple[str, Callable[[], tuple[list[dict[str, Any]], bool] | None]]] = [
        ("keys", lambda: _paged(system, gateway, "/key/list", "keys", "size")),
        ("users", lambda: _paged(system, gateway, "/user/list", "users", "page_size")),
    ]
    for what, read in lists:
        answer = read()
        if answer is None:
            found.problems.append(f"its {what} (/{what[:-1]}/list)")
            continue
        rows, capped = answer
        if capped:
            found.capped.append(what)
        if what == "keys":
            found.keys = _ranked([allowance(r, ("key_alias",), "key_alias") for r in rows])
        else:
            found.users = _ranked(
                [allowance(r, ("user_alias", "user_id"), "user_id") for r in rows]
            )
    teams = system.get_json(f"{gateway.base}/team/list", gateway.headers)
    if isinstance(teams, list):
        found.teams = _ranked(
            [
                allowance(t, ("team_alias", "team_id"), "team_id")
                for t in teams
                if isinstance(t, dict)
            ]
        )
    else:
        found.problems.append("its teams (/team/list)")


def read_state(settings: AdminSettings, system: System) -> GatewayState:
    """Ask the gateway how it is set up. One that cannot be asked is named in `error`; a part
    that does not answer is named in `problems`."""
    gateway = connect(settings, system)
    if gateway is None:
        return GatewayState()
    if isinstance(gateway, str):
        return GatewayState(configured=True, error=gateway)
    found = GatewayState(configured=True)
    health = system.get_json(f"{gateway.base}/health/readiness", gateway.headers)
    if not isinstance(health, dict):
        return GatewayState(configured=True, error=f"the gateway at {gateway.base} did not answer")
    found.database = _text(health.get("db"))
    found.version = _text(health.get("litellm_version"))
    found.ready = health.get("status") in {"healthy", "connected"}
    info = system.get_json(f"{gateway.base}/model/info", gateway.headers)
    if isinstance(info, dict):
        found.models = models_from(info)
    else:
        found.problems.append("its models (/model/info)")
    _read_lists(system, gateway, found)
    return found
