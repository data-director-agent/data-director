"""A data steward's list of the projects they may see (docs/specs/stewardship.md, invariant 3;
#232).

Which projects are listed is the steward path's decision (`dd_harness.steward_access`), never
the shell's: the projects that name one of the steward's teams in the listing index (an
escalation routed to it, a pause it holds, or its choice as support team), kept where
`access_in` gives the steward access. So a member of a project, a deleted project, and, unless
the profile sets `visibility: scope`, a project that only chose the team as its support team,
are not listed. Each team's projects are one indexed read, as the team's queue is.

Listing a project is a read of it: each project on the page returned is recorded as viewed by
the steward (`steward_viewed`, at most once a day), as opening it is, and the researcher sees
it. A project on another page is not.

Each row is the project's summary, as a person's own list gives it, with what a steward needs
beside it: who owns it, through which of the steward's teams they reach it, its live
escalations and its pause, its latest runs and their outcomes, what awaits a person's review,
and what the steward may do there (`permitted_actions`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from dd_harness.listing import Page, Readable, check_limit
from dd_harness.policy import Profile
from dd_harness.projects import OWNER, member_roles
from dd_harness.projects.escalations import LIVE_STATES, escalations
from dd_harness.projects.facts import open_proposals
from dd_harness.projects.stewarding import gate_decisions, pause_of, viewed_today
from dd_harness.role_events import team_key
from dd_harness.steward_access import StewardAccess, access_in
from dd_harness.steward_api import permitted_actions_in
from dd_harness.storage import ProjectStorage, RunStorage
from dd_sdk.contract.models import Principal, now

# How many of a project's latest runs a row shows.
RECENT_RUNS: Final = 5
# A page too large to fill: the runs of a page of projects are read in one scan.
_EVERY: Final = 10**9
# The outcome of a run the policy gate referred to a steward (docs/specs/policy-and-identity.md).
_GATED: Final = ("referred", "policy_requires_approval")

type Visible = dict[str, tuple[list[dict[str, Any]], StewardAccess]]


def visible(store: ProjectStorage, profile: Profile, steward: Principal) -> Visible:
    """Each project `steward` may see as a steward, with its log and their access to it, the one
    created last first. A project that names two of their teams is listed once."""
    found: Visible = {}
    for team in profile.stewardship.teams_of(steward.principal_id):
        for project_id, events in store.logs_naming(team_key(team.team_id)).items():
            if project_id in found:
                continue
            access = access_in(profile, events, steward)
            if access is not None:
                found[project_id] = (events, access)
    # Project identifiers are UUIDv7, so they sort in the order the projects were created.
    return dict(sorted(found.items(), reverse=True))


def listing(
    store: ProjectStorage,
    runs: RunStorage,
    profile: Profile,
    steward: Principal,
    *,
    limit: int,
    before: str | None = None,
    caused_by: str,
) -> Page:
    """A page of the projects `steward` may see, the one created last first, each recorded as
    viewed by them. The cursor is the last listed project; one that names no project they may
    see names an empty page."""
    check_limit(limit)
    projects = visible(store, profile, steward)
    ids = list(projects)
    if before is not None:
        if before not in ids:
            return Page([])
        ids = ids[ids.index(before) + 1 :]
    page, more = ids[:limit], len(ids) > limit
    latest = _latest_runs(runs, steward, page)
    rows = []
    for project_id in page:
        events, access = projects[project_id]
        rows.append(_row(store, profile, steward, project_id, events, access, latest))
        _record_view(store, steward, project_id, events, caused_by)
    return Page(rows, page[-1] if more else None)


def _row(
    store: ProjectStorage,
    profile: Profile,
    steward: Principal,
    project_id: str,
    events: list[dict[str, Any]],
    access: StewardAccess,
    latest: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    summary = store.summary_of(project_id, events)
    project_runs = latest.get(project_id, [])
    decided = gate_decisions(events)
    return {
        **summary,
        "owners": [m for m, role in member_roles(events).items() if role == OWNER],
        "access": {
            "teams": [_team(profile, t) for t in sorted(access.teams)],
            "escalated": access.escalated,
            "holds_pause": access.holds_pause,
        },
        "escalations": [
            {k: e[k] for k in ("escalation_id", "state", "team_id", "opened_at")}
            for e in escalations(events)
            if e["state"] in LIVE_STATES and e["team_id"] in access.teams
        ],
        "paused": pause_of(events),
        "recent_runs": project_runs[:RECENT_RUNS],
        "awaiting_review": {
            "proposed_versions": summary["documents"]["proposed"],
            "fact_proposals": len(open_proposals(events)),
            "referred_runs": [
                r["invocation_id"]
                for r in project_runs
                if (r["status"], r["reason_code"]) == _GATED and r["invocation_id"] not in decided
            ],
        },
        "permitted_actions": permitted_actions_in(profile, events, steward),
    }


def _team(profile: Profile, team_id: str) -> dict[str, str]:
    team = profile.stewardship.team(team_id)
    return {"team_id": team_id, "name": team.name if team else team_id}


def _latest_runs(
    runs: RunStorage, steward: Principal, project_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """The runs in each of `project_ids`, newest first, from one scan of the run store. The
    steward's own runs in no project, which the scan also gives, are left out."""
    if not project_ids:
        return {}
    wanted = frozenset(project_ids)
    readable = Readable(steward.principal_id, project_ids=wanted)
    found: dict[str, list[dict[str, Any]]] = {}
    for run in runs.list_runs(readable=readable, limit=_EVERY).items:
        if run["project_id"] in wanted:
            found.setdefault(run["project_id"], []).append(run)
    return found


def _record_view(
    store: ProjectStorage,
    steward: Principal,
    project_id: str,
    events: list[dict[str, Any]],
    caused_by: str,
) -> None:
    """Record that `steward` saw the project, unless the log just read shows they did today
    (`record_view` checks again, under the project's lock)."""
    if not viewed_today(events, steward.principal_id, now().date().isoformat()):
        store.record_view(project_id, acted_for=steward, caused_by=caused_by)
