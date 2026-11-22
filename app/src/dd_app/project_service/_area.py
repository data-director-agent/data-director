"""What every area of the project service shares: the way to the projects' logs, and the errors
its rules raise."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_app.governance import Governance
from dd_harness.policy import Profile
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

    @property
    def _profile(self) -> Profile:
        """The deployment's profile, which the harness's checks are made against."""
        return self.governance.conductor.profile

    def _envelope(self, invocation_id: str) -> Mapping[str, Any] | None:
        """A stored run's envelope, from the run store, never from what a request says of it."""
        return self.governance.conductor.store.get(invocation_id)
