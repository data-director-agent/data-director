"""What the app's routes may do with projects: the one way they reach the projects' logs.

Each method is one thing a route does, and answers with what the route then shows, read back
from the log. The harness decides and records (`dd_harness.projects`); this package holds the
app's own rules about a request, such as that a project is deleted only by someone who typed its
name, and wires the harness's pieces together, such as the pinned re3data export a repository
choice resolves against. Every method blocks, so a route calls it off the event loop.

The methods are grouped by area, one class each, as `dd_harness.projects` and the route modules
are: a route names the area it uses (`deps.projects.deposit.validate`).

Whom a change acts for is always the principal the authenticator names, never a request's body,
and `caused_by` is the request that caused it (docs/specs/projects.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from dd_app.governance import Governance
from dd_app.project_service._area import RepositoriesUnavailableError, TitleMismatchError
from dd_app.project_service.deposit import REPOSITORY_SEARCH_LIMIT, Deposit
from dd_app.project_service.drafts import Documents, Facts
from dd_app.project_service.lifecycle import Lifecycle
from dd_app.project_service.materials import Materials
from dd_app.project_service.progress import Progress
from dd_harness.deposit import PackageRefusedError


@dataclass(frozen=True)
class ProjectService:
    """Every area, each over the same governance."""

    lifecycle: Lifecycle
    materials: Materials
    progress: Progress
    documents: Documents
    facts: Facts
    deposit: Deposit

    @classmethod
    def over(cls, governance: Governance) -> ProjectService:
        return cls(
            lifecycle=Lifecycle(governance),
            materials=Materials(governance),
            progress=Progress(governance),
            documents=Documents(governance),
            facts=Facts(governance),
            deposit=Deposit(governance),
        )


__all__ = [
    "REPOSITORY_SEARCH_LIMIT",
    "PackageRefusedError",
    "ProjectService",
    "RepositoriesUnavailableError",
    "TitleMismatchError",
]
