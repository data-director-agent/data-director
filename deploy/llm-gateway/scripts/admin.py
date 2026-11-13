#!/usr/bin/env python3
"""Small admin CLI for the LiteLLM gateway (standard library only).

Reads LITELLM_URL (default http://localhost:4000) and LITELLM_MASTER_KEY from the
environment, falling back to the .env file next to compose.yaml.

Examples
  scripts/admin.py team create nlp-lab --budget 200 --period 30d
  scripts/admin.py user create someone@example.ac.uk --budget 50 --period 30d --team <team_id>
  scripts/admin.py key create thesis-ch3 --team <team_id> --user <user_id> \
        --budget 25 --period 30d --models claude-sonnet-5-5,gemini --tags project:thesis,grant:EP-X-1
  scripts/admin.py key info sk-...            # spend vs budget for one key
  scripts/admin.py team list                  # all teams with spend vs budget
  scripts/admin.py spend --by tag             # this month, grouped by tag
  scripts/admin.py spend --by team --start 2026-10-01 --end 2026-10-31
  scripts/admin.py export --start 2026-10-01 --end 2026-10-31 --out oct.csv
  scripts/admin.py metrics-key                # read-only key for Prometheus
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- config
def _load_dotenv() -> dict[str, str]:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_DOTENV = _load_dotenv()
BASE_URL = os.environ.get("LITELLM_URL", "http://localhost:4000").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY") or _DOTENV.get("LITELLM_MASTER_KEY")


# --------------------------------------------------------------------------- http
def api(method: str, path: str, body: dict | None = None, params: dict | None = None) -> Any:
    if not MASTER_KEY:
        sys.exit("LITELLM_MASTER_KEY not set (environment or .env).")
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {MASTER_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {path}: {e.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach gateway at {BASE_URL}: {e.reason}")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, [], {})}


def _csv_list(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _money(x: float | None) -> str:
    return "—" if x is None else f"${x:,.4f}"


def _print_budget(
    label: str,
    spend: float,
    budget: float | None,
    period: str | None = None,
    reset_at: str | None = None,
) -> None:
    pct = f" ({spend / budget:.0%})" if budget else ""
    extra = f", resets every {period}" if period else ""
    extra += f" (next {reset_at[:10]})" if reset_at else ""
    print(f"{label}: spent {_money(spend)} of {_money(budget)}{pct}{extra}")


# --------------------------------------------------------------------------- commands
def team_create(a: argparse.Namespace) -> None:
    r = api(
        "POST",
        "/team/new",
        _clean(
            {
                "team_alias": a.alias,
                "max_budget": a.budget,
                "budget_duration": a.period,
                "models": _csv_list(a.models),
                "tpm_limit": a.tpm,
                "rpm_limit": a.rpm,
            }
        ),
    )
    print(f"team_id: {r['team_id']}  (alias {r.get('team_alias')})")


def team_list(a: argparse.Namespace) -> None:
    teams = api("GET", "/team/list")
    for t in teams:
        _print_budget(
            f"{t.get('team_alias') or '(no alias)'} [{t['team_id']}]",
            t.get("spend", 0),
            t.get("max_budget"),
            t.get("budget_duration"),
            t.get("budget_reset_at"),
        )


def team_info(a: argparse.Namespace) -> None:
    t = api("GET", "/team/info", params={"team_id": a.team_id})["team_info"]
    _print_budget(
        t.get("team_alias") or a.team_id,
        t.get("spend", 0),
        t.get("max_budget"),
        t.get("budget_duration"),
        t.get("budget_reset_at"),
    )


def user_create(a: argparse.Namespace) -> None:
    r = api(
        "POST",
        "/user/new",
        _clean(
            {
                "user_email": a.email,
                "user_id": a.user_id,
                "max_budget": a.budget,
                "budget_duration": a.period,
                "teams": [a.team] if a.team else None,
                "models": _csv_list(a.models),
            }
        ),
    )
    print(f"user_id: {r['user_id']}")
    if r.get("key"):
        print(f"key:     {r['key']}   (personal key created automatically; store it safely)")


def user_info(a: argparse.Namespace) -> None:
    u = api("GET", "/user/info", params={"user_id": a.user_id})["user_info"]
    _print_budget(
        u.get("user_email") or a.user_id,
        u.get("spend", 0),
        u.get("max_budget"),
        u.get("budget_duration"),
        u.get("budget_reset_at"),
    )


def key_create(a: argparse.Namespace) -> None:
    metadata = {"tags": _csv_list(a.tags)} if a.tags else None
    r = api(
        "POST",
        "/key/generate",
        _clean(
            {
                "key_alias": a.alias,
                "team_id": a.team,
                "user_id": a.user,
                "max_budget": a.budget,
                "budget_duration": a.period,
                "models": _csv_list(a.models),
                "tpm_limit": a.tpm,
                "rpm_limit": a.rpm,
                "duration": a.expires,
                "metadata": metadata,
            }
        ),
    )
    print(f"key: {r['key']}")
    print("Store it now: it cannot be shown again.")


def key_info(a: argparse.Namespace) -> None:
    i = api("GET", "/key/info", params={"key": a.key})["info"]
    _print_budget(
        i.get("key_alias") or i.get("key_name") or "key",
        i.get("spend", 0),
        i.get("max_budget"),
        i.get("budget_duration"),
        i.get("budget_reset_at"),
    )


def metrics_key(a: argparse.Namespace) -> None:
    """Read-only admin-viewer key for Prometheus, written to monitoring/litellm_key."""
    r = api(
        "POST",
        "/user/new",
        {"user_id": a.user_id, "user_role": "proxy_admin_viewer", "max_budget": 0},
    )
    if not r.get("key"):
        sys.exit("No key returned; does the user already exist? Use another --user-id.")
    out = ROOT / "monitoring" / "litellm_key"
    out.write_text(r["key"] + "\n")
    out.chmod(0o644)  # Prometheus runs as "nobody"; the key is read-only with a $0 budget
    print(f"Wrote read-only metrics key for user '{r['user_id']}' to {out.relative_to(ROOT)}")


# --------------------------------------------------------------------------- spend logs
def _date_range(a: argparse.Namespace) -> tuple[str, str]:
    today = dt.datetime.now(dt.UTC).astimezone().date()  # local date
    start = dt.date.fromisoformat(a.start) if a.start else today.replace(day=1)
    end = dt.date.fromisoformat(a.end) if a.end else today
    return f"{start} 00:00:00", f"{end} 23:59:59"


def fetch_logs(a: argparse.Namespace) -> list[dict]:
    start, end = _date_range(a)
    rows, page = [], 1
    while True:
        r = api(
            "GET",
            "/spend/logs/v2",
            params={
                "start_date": start,
                "end_date": end,
                "page": page,
                "page_size": 1000,
                "team_id": getattr(a, "team", None),
                "user_id": getattr(a, "user", None),
                "model": getattr(a, "model", None),
            },
        )
        rows.extend(r.get("data", []))
        if r.get("total_is_capped"):
            print(
                "warning: the API caps results at 10,000 rows; narrow the date range "
                "or query Postgres directly (see README).",
                file=sys.stderr,
            )
        if page >= r.get("total_pages", 1):
            return rows
        page += 1


def _keys_for(row: dict, by: str, include_ua: bool) -> list[str]:
    md = row.get("metadata") or {}
    if by == "tag":
        tags = [
            t
            for t in (row.get("request_tags") or [])
            if include_ua or not t.startswith("User-Agent:")
        ]
        return tags or ["(untagged)"]
    if by == "team":
        return [md.get("user_api_key_team_alias") or row.get("team_id") or "(no team)"]
    if by == "user":
        return [md.get("user_api_key_user_email") or md.get("user_api_key_user_id") or "(no user)"]
    if by == "key":
        return [md.get("user_api_key_alias") or (row.get("api_key") or "")[:12] or "(unknown)"]
    if by == "model":
        return [row.get("model_group") or row.get("model") or "(unknown)"]
    if by == "day":
        return [(row.get("startTime") or "")[:10]]
    raise ValueError(by)


def spend(a: argparse.Namespace) -> None:
    rows = fetch_logs(a)
    agg = defaultdict(lambda: [0, 0, 0, 0.0])  # requests, in, out, cost
    for row in rows:
        for k in _keys_for(row, a.by, a.include_user_agent):
            s = agg[k]
            s[0] += 1
            s[1] += row.get("prompt_tokens") or 0
            s[2] += row.get("completion_tokens") or 0
            s[3] += row.get("spend") or 0.0
    start, end = _date_range(a)
    print(f"Spend by {a.by}, {start[:10]} to {end[:10]} ({len(rows)} requests)\n")
    w = max([len(a.by), *(len(k) for k in agg)])
    print(
        f"{a.by:<{w}}  {'requests':>8}  {'in tokens':>12}  {'out tokens':>12}  {'cost (USD)':>12}"
    )
    for k, (n, i, o, c) in sorted(agg.items(), key=lambda kv: -kv[1][3]):
        print(f"{k:<{w}}  {n:>8}  {i:>12,}  {o:>12,}  {c:>12.4f}")
    total = sum(r.get("spend") or 0 for r in rows)
    print(f"\nTotal cost: ${total:,.4f}")
    if a.by == "tag":
        print(
            "Note: a request with several tags counts towards each, so tag rows can sum to more than the total."
        )


EXPORT_FIELDS = [
    "startTime",
    "request_id",
    "status",
    "model_group",
    "model",
    "custom_llm_provider",
    "team_id",
    "team_alias",
    "key_alias",
    "user",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "spend",
    "request_tags",
]


def _write_csv(rows: list[dict], out: TextIO) -> None:
    w = csv.DictWriter(out, fieldnames=EXPORT_FIELDS)
    w.writeheader()
    for r in rows:
        md = r.get("metadata") or {}
        w.writerow(
            {
                **{f: r.get(f) for f in EXPORT_FIELDS},
                "team_alias": md.get("user_api_key_team_alias"),
                "key_alias": md.get("user_api_key_alias"),
                "user": md.get("user_api_key_user_email") or md.get("user_api_key_user_id"),
                "request_tags": ";".join(
                    t for t in (r.get("request_tags") or []) if not t.startswith("User-Agent:")
                ),
            }
        )


def export(a: argparse.Namespace) -> None:
    rows = fetch_logs(a)
    if a.out == "-":
        _write_csv(rows, sys.stdout)
        return
    with Path(a.out).open("w", newline="") as out:
        _write_csv(rows, out)
    print(f"Wrote {len(rows)} rows to {a.out}")


# --------------------------------------------------------------------------- CLI
def _limits(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--budget", type=float, help="max spend in USD")
    sp.add_argument("--period", help="budget reset period, e.g. 30d, 7d, 24h")
    sp.add_argument("--models", help="comma-separated model names allowed")


def _rates(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--tpm", type=int, help="tokens per minute")
    sp.add_argument("--rpm", type=int, help="requests per minute")


def _window(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--start", help="YYYY-MM-DD (default: first of this month)")
    sp.add_argument("--end", help="YYYY-MM-DD inclusive (default: today)")
    sp.add_argument("--team", help="filter by team_id")
    sp.add_argument("--user", help="filter by user_id")
    sp.add_argument("--model", help="filter by model")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    team = sub.add_parser("team").add_subparsers(dest="sub", required=True)
    sp = team.add_parser("create")
    sp.add_argument("alias")
    _limits(sp)
    _rates(sp)
    sp.set_defaults(fn=team_create)
    team.add_parser("list").set_defaults(fn=team_list)
    sp = team.add_parser("info")
    sp.add_argument("team_id")
    sp.set_defaults(fn=team_info)

    user = sub.add_parser("user").add_subparsers(dest="sub", required=True)
    sp = user.add_parser("create")
    sp.add_argument("email")
    _limits(sp)
    sp.add_argument("--user-id", help="custom user_id (default: generated)")
    sp.add_argument("--team", help="team_id to add the user to")
    sp.set_defaults(fn=user_create)
    sp = user.add_parser("info")
    sp.add_argument("user_id")
    sp.set_defaults(fn=user_info)

    key = sub.add_parser("key").add_subparsers(dest="sub", required=True)
    sp = key.add_parser("create")
    sp.add_argument("alias")
    _limits(sp)
    _rates(sp)
    sp.add_argument("--team")
    sp.add_argument("--user")
    sp.add_argument("--tags", help="comma-separated tags applied to every request with this key")
    sp.add_argument("--expires", help="key lifetime, e.g. 90d")
    sp.set_defaults(fn=key_create)
    sp = key.add_parser("info")
    sp.add_argument("key")
    sp.set_defaults(fn=key_info)

    sp = sub.add_parser("spend", help="summarise spend from the request logs")
    _window(sp)
    sp.add_argument("--by", choices=["tag", "team", "user", "key", "model", "day"], default="team")
    sp.add_argument(
        "--include-user-agent",
        action="store_true",
        help="keep the automatic 'User-Agent: ...' tags",
    )
    sp.set_defaults(fn=spend)

    sp = sub.add_parser("export", help="export request logs to CSV")
    _window(sp)
    sp.add_argument("--out", default="-", help="file path, or - for stdout")
    sp.set_defaults(fn=export)

    sp = sub.add_parser("metrics-key", help="create a read-only key for Prometheus scraping")
    sp.add_argument("--user-id", default="prometheus")
    sp.set_defaults(fn=metrics_key)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:  # e.g. `admin.py export | head`
        sys.stderr.close()
