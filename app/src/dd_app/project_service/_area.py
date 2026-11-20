"""What every area of the project service shares: the way to the projects' logs, and the errors
its rules raise."""

from __future__ import annotations

from dataclasses import dataclass

from dd_app.governance import Governance
from dd_harness.projects import ProjectError, UnknownProjectError
from dd_harness.storage import ProjectStorage


class TitleMismatchError(ProjectError):
    """The name typed to delete a project is not its name."""


class RepositoriesUnavailableError(Exception):
    """This server has no repository requirement sets, so no repository can be chosen."""


@dataclass(frozen=True)
class Area:
    """One area of what routes may do with projects, over the logs `governance` holds."""

    governance: Governance

    @property
    def _store(self) -> ProjectStorage:
        if self.governance.projects is None:
            raise UnknownProjectError("this server keeps no projects")
        return self.governance.projects
