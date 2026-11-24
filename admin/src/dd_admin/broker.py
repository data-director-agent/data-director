"""The model broker as its operators need to see it (docs/guide/operations/admin.md, "Broker").

The broker's store is readable by its own user alone, so the admin service asks the broker
instead: `GET /admin/summary` (`dd_broker.admin`), with the operators' credential
(`deploy/broker-admin-credential.sh`). The answer is aggregate: people's own accounts counted by
provider and tokens summed over everyone, never a pseudonym, label or key. `/healthz` says
whether the broker is up without the credential.

The page compares the agents that hold a broker credential with those whose cards declare models,
since a model-backed agent without one cannot call through the broker.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from dd_admin.agents import Agents
from dd_admin.settings import AdminSettings
from dd_admin.system import System

SUMMARY_PATH = "/admin/summary"


@dataclass(frozen=True)
class Tokens:
    input: int = 0
    output: int = 0

    def __add__(self, other: Tokens) -> Tokens:
        return Tokens(self.input + other.input, self.output + other.output)

    @property
    def total(self) -> int:
        return self.input + self.output


@dataclass
class BrokerState:
    """What the broker says. `error` is set when it could not be asked; `summary_error` when it
    is up but its summary was not given."""

    configured: bool = False
    error: str | None = None
    summary_error: str | None = None
    days: int = 30
    accounts_by_provider: dict[str, int] = field(default_factory=dict)
    people_with_usage: int = 0
    per_day: list[tuple[str, int]] = field(default_factory=list)  # oldest first
    by_payer: dict[str, Tokens] = field(default_factory=dict)
    by_model: list[tuple[str, str, str, Tokens]] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    providers_paid: list[str] = field(default_factory=list)
    through_base_url: bool = False
    allowed_base_urls: list[str] = field(default_factory=list)
    private_base_urls: list[str] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return self.configured and self.error is None

    @property
    def summarised(self) -> bool:
        return self.answered and self.summary_error is None


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def summarise(doc: dict[str, Any], found: BrokerState) -> None:
    """Fill `found` from the broker's summary."""
    found.days = _count(doc.get("days")) or found.days
    accounts = doc.get("accounts_by_provider")
    if isinstance(accounts, dict):
        found.accounts_by_provider = {str(k): _count(v) for k, v in sorted(accounts.items())}
    found.people_with_usage = _count(doc.get("people_with_usage"))
    per_day: defaultdict[str, int] = defaultdict(int)
    by_payer: defaultdict[str, Tokens] = defaultdict(Tokens)
    by_model: defaultdict[tuple[str, str, str], Tokens] = defaultdict(Tokens)
    rows = doc.get("usage")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        tokens = Tokens(_count(row.get("input_tokens")), _count(row.get("output_tokens")))
        payer = str(row.get("payer") or "unknown")
        per_day[str(row.get("day") or "")] += tokens.total
        by_payer[payer] += tokens
        by_model[(str(row.get("provider") or "—"), str(row.get("model") or "—"), payer)] += tokens
    found.per_day = _every_day(doc.get("since"), found.days, per_day)
    found.by_payer = dict(sorted(by_payer.items()))
    found.by_model = sorted(
        ((p, m, payer, t) for (p, m, payer), t in by_model.items()), key=lambda r: -r[3].total
    )
    found.agents = sorted(_strings(doc.get("agents")))
    found.providers_paid = sorted(_strings(doc.get("providers_paid")))
    found.through_base_url = doc.get("deployment_base_url") is True
    found.allowed_base_urls = _strings(doc.get("allowed_base_urls"))
    found.private_base_urls = _strings(doc.get("private_base_urls"))


def _every_day(since: object, days: int, counts: dict[str, int]) -> list[tuple[str, int]]:
    """`counts` on each of `days` days from `since`, with 0 for a day without calls, as the
    Spend page charts its days. Without a valid `since`, the days that have counts."""
    try:
        first = date.fromisoformat(str(since))
    except ValueError:
        return sorted((d, n) for d, n in counts.items() if d)
    every = [(first + timedelta(days=n)).isoformat() for n in range(days)]
    return [(d, counts.get(d, 0)) for d in every]


def read_broker(settings: AdminSettings, system: System) -> BrokerState:
    """Ask the broker whether it is up, then for its summary."""
    if not settings.broker_url:
        return BrokerState()
    base = settings.broker_url
    health = system.get_json(f"{base}/healthz")
    if not isinstance(health, dict) or health.get("status") != "ok":
        return BrokerState(configured=True, error=f"the model broker at {base} did not answer")
    found = BrokerState(configured=True)
    if settings.broker_key_file is None:
        found.summary_error = (
            "no credential for its summary: run deploy/broker-admin-credential.sh, or set "
            "DD_ADMIN_BROKER_KEY_FILE"
        )
        return found
    key = (system.read_text(settings.broker_key_file) or "").strip()
    if not key:
        found.summary_error = f"the credential at {settings.broker_key_file} cannot be read"
        return found
    doc = system.get_json(f"{base}{SUMMARY_PATH}", {"Authorization": f"Bearer {key}"})
    if not isinstance(doc, dict):
        found.summary_error = (
            "it did not give its summary: the broker may lack DD_BROKER_ADMIN_CREDENTIAL, or hold "
            "another credential's digest (run deploy/broker-admin-credential.sh again)"
        )
        return found
    summarise(doc, found)
    return found


@dataclass(frozen=True)
class Coverage:
    """Which agents can call through the broker, against which need to."""

    model_backed: list[str]  # agents in agents.yaml whose cards declare models, by agent id
    missing: list[str]  # model-backed, but holding no broker credential
    unused: list[str]  # holding a credential, but not a model-backed agent in agents.yaml


def broker_id(name: str) -> str:
    """The id the broker knows an agent by: a dot where its configured name has its first
    hyphen (`advisor-standards` is `advisor.standards`), as `deploy/broker-credentials.sh` has
    it."""
    return name.replace("-", ".", 1)


def coverage(found: BrokerState, agents: Agents) -> Coverage | None:
    """Compare the broker's agents with the model-backed ones that answered. None without both."""
    if not found.summarised or not agents.agents:
        return None
    backed = sorted(
        str(a.described.get("agent_id") or broker_id(a.name))
        for a in agents.agents
        if a.state == "up" and a.described.get("models")
    )
    held = set(found.agents)
    return Coverage(
        model_backed=backed,
        missing=[a for a in backed if a not in held],
        unused=sorted(held - set(backed)),
    )
