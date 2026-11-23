"""What a reader is answered with about stored work: the conversations, projects and runs they
may read (#153, docs/specs/app.md).

`Governance` says who may read what; this module lists and reads back what it allows, so that a
refusal looks like absence and does not reveal whether something exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dd_app.governance import CONVERSATION_ID, CREATED_BY_ROUTE, Governance
from dd_app.run_checks import stored_checks
from dd_harness import conversations, project_access
from dd_harness.listing import Page, Readable, check_limit
from dd_harness.steward_api import permitted_actions_in
from dd_harness.transport.paging import PAGE_SIZE
from dd_sdk.contract.models import Principal

RUN_ID = re.compile(r"[0-9A-Za-z-]{1,64}")
# A page too large to fill: asking for it at once reads the store once, not once a page.
EVERY = 10**9
# What `GET /api/projects` says of each conversation in a project.
LISTED_CONVERSATION = ("conversation_id", "title", "started_at", "last_completed_at", "turns")


@dataclass(frozen=True)
class Reads:
    governance: Governance

    def conversations(
        self, reader: Principal, *, limit: int = PAGE_SIZE, before: str | None = None
    ) -> Page:
        """A page of the stored conversations `reader` may read, most recently active first
        (`GET /api/conversations`). One started but given no turn yet is not listed."""
        return conversations.list_conversations(
            self.governance.conductor.store,
            readable=self.governance.readable(reader),
            limit=limit,
            before=before,
        )

    def projects_for(
        self, principal: Principal, *, limit: int = PAGE_SIZE, before: str | None = None
    ) -> Page:
        """A page of the projects `principal` may read, the one created last first
        (`GET /api/projects`): each project's summary, with what they may do there and the
        conversations started in it that have a turn, most recently active first, so that the
        shell can name a project the app created untitled. A project the app created for a
        conversation, with nothing in it yet (no conversation with a turn, no inventory and no
        document), is not listed, as a conversation with no turn is not; one a person created
        with `POST /api/projects` is. The cursor is the last listed project; one that names no
        project the person may read names an empty page."""
        check_limit(limit)
        if self.governance.projects is None:
            return Page([])
        logs = project_access.readable_logs(self.governance.projects, principal)
        newest_first = list(reversed(logs))
        if before is not None:
            if before not in newest_first:
                return Page([])
            newest_first = newest_first[newest_first.index(before) + 1 :]
        found: list[dict[str, Any]] = []
        every = self._every_conversation(project_access.readable_from(principal, logs))
        for project_id in newest_first:
            summary = self.governance.projects.summary_of(project_id, logs[project_id])
            listed = [
                {key: c.get(key) for key in LISTED_CONVERSATION}
                for c in every
                if c.get("project_id") == project_id
            ]
            if (
                not listed
                and summary["inventory"] is None
                and not any(summary["documents"].values())
                and logs[project_id][0]["caused_by"] != CREATED_BY_ROUTE
            ):
                continue
            if len(found) == limit:
                return Page(found, found[-1]["project_id"])
            permitted = permitted_actions_in(
                self.governance.conductor.profile, logs[project_id], principal
            )
            found.append({**summary, "conversations": listed, "permitted_actions": permitted})
        return Page(found)

    def deleted_projects_for(
        self, owner: Principal, *, limit: int = PAGE_SIZE, before: str | None = None
    ) -> Page:
        """A page of the deleted projects `owner` may still restore, the one deleted last first
        (`GET /api/projects/deleted`, docs/specs/projects.md, invariant 23): each project's
        summary, whose `deleted` says when, by whom and until when. One whose restore period is
        over is not listed, since the app can no longer restore it. The cursor is the last
        listed project."""
        check_limit(limit)
        if self.governance.projects is None:
            return Page([])
        now = datetime.now(UTC)
        summaries = [
            self.governance.projects.summary(project_id)
            for project_id in project_access.deleted_projects(self.governance.projects, owner)
        ]
        restorable = sorted(
            (
                s
                for s in summaries
                if datetime.fromisoformat(s["deleted"]["restorable_until"]) > now
            ),
            key=lambda s: s["deleted"]["at"],
            reverse=True,
        )
        if before is not None:
            ids = [s["project_id"] for s in restorable]
            if before not in ids:
                return Page([])
            restorable = restorable[ids.index(before) + 1 :]
        if len(restorable) > limit:
            return Page(restorable[:limit], restorable[limit - 1]["project_id"])
        return Page(restorable)

    def _every_conversation(self, readable: Readable) -> list[dict[str, Any]]:
        """Every conversation `readable` includes, most recently active first, from one scan of
        the run store: as many as the reader has, whatever the size of the store."""
        return conversations.list_conversations(
            self.governance.conductor.store, readable=readable, limit=EVERY
        ).items

    def conversation(self, conversation_id: str, reader: Principal) -> dict[str, Any] | None:
        """A conversation as `dd_harness.conversations` derives it (`GET /api/conversations/{id}`),
        or None, also when `reader` may not read it, so that a refusal does not reveal whether it
        exists. One started but given no turn yet has no turns."""
        if not CONVERSATION_ID.fullmatch(conversation_id):
            return None
        found = self.governance.stored_conversation(conversation_id)
        if found is None or not self.governance.may_read_conversation(conversation_id, reader):
            return None
        return found

    def runs(self, reader: Principal, *, limit: int = PAGE_SIZE, before: str | None = None) -> Page:
        """A page of the stored runs `reader` may read, newest first (`GET /api/runs`)."""
        return self.governance.conductor.store.list_runs(
            readable=self.governance.readable(reader), limit=limit, before=before
        )

    def project_runs(
        self, project_id: str, reader: Principal, payload_class: str, *, limit: int = PAGE_SIZE
    ) -> list[dict[str, Any]]:
        """The envelopes of the succeeded runs in project `project_id` whose payload is a
        `payload_class`, newest first, at most `limit` (`GET /api/projects/{id}/runs`): turns and
        delegated children alike, from the conversations `reader` may read. The caller names the
        class, so the server names none (docs/specs/app.md)."""
        check_limit(limit)
        readable = self.governance.readable(reader)
        store = self.governance.conductor.store
        found: list[dict[str, Any]] = []
        for listed in self._every_conversation(readable):
            if listed.get("project_id") != project_id:
                continue
            found += (
                envelope
                for envelope in store.iter_envelopes(conversation_id=listed["conversation_id"])
                if envelope.get("project_id") == project_id
                and envelope["outcome"]["status"] == "succeeded"
                and (envelope.get("payload") or {}).get("schema_class") == payload_class
                and readable.includes(envelope)
            )
        found.sort(key=lambda envelope: envelope["completed_at"], reverse=True)
        return found[:limit]

    def stored_run(self, invocation_id: str, reader: Principal) -> dict[str, Any] | None:
        """A stored run as `run` returned it, with its request (`GET /api/runs/{id}`), or None,
        also when `reader` may not read it, so that a refusal does not reveal whether it exists.

        Only an identifier made of letters, digits and hyphens names a run, so no path outside
        the store can be read.
        """
        if not RUN_ID.fullmatch(invocation_id):
            return None
        store = self.governance.conductor.store
        envelope = store.get(invocation_id)
        if envelope is None or not self.governance.may_read_run(envelope, reader):
            return None
        return {
            "envelope": envelope,
            "request": store.get_request(invocation_id),
            "checks": self.checks(invocation_id),
        }

    def checks(self, invocation_id: str) -> dict[str, Any]:
        """What the grounding linter and the source check reported on a run."""
        return stored_checks(self.governance.conductor.store, invocation_id)
