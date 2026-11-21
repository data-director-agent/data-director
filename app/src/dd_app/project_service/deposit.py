"""Repository choice and deposit (docs/specs/deposit.md)."""

from __future__ import annotations

from typing import Any

from dd_app import deposit
from dd_app.project_service._area import Area, RepositoriesUnavailableError
from dd_harness import deposit_api, institution_repositories
from dd_harness.deposit import Package, Validation, build_package, check
from dd_harness.disclosure import Disclosure, disclose
from dd_harness.requirements import Requirements
from dd_harness.storage import (
    DepositSource,
    ProjectDeposits,
    ProjectDocuments,
    ProjectRecord,
    ProjectRepository,
)
from dd_sdk.contract.models import Principal

# The most repositories one search of the pinned re3data export answers with.
REPOSITORY_SEARCH_LIMIT = 20


class Deposit(Area):
    @property
    def offers_repositories(self) -> bool:
        """Whether this server has repository requirement sets, so that one may be chosen."""
        return self.governance.requirements is not None

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        store: ProjectRepository = self._store
        return store.requirements(project_id)

    def choose_repository(
        self, project_id: str, repository_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any] | None:
        """The researcher's choice, by its re3data or DataCite identifier alone: its name and
        declared standards come from the pinned registry, resolved against the deployment's
        requirement sets. A change is a new choice, and the last one counts."""
        store, requirements = self._store, self._requirements()
        store.choose_repository(
            project_id,
            repository_id,
            registry=self.governance.conductor.sources,
            requirements=requirements,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return store.requirements(project_id)

    def _requirements(self) -> Requirements:
        if self.governance.requirements is None:
            raise RepositoriesUnavailableError("This server has no repository requirement sets.")
        return self.governance.requirements

    def search_repositories(self, query: str) -> dict[str, Any]:
        """Those the pinned registries hold that `query` names, or, without one, those the
        deployment suggests: the repositories its profile names as its institution's, then its
        overrides, then `suggested.yaml`."""
        conductor, requirements = self.governance.conductor, self.governance.requirements
        sources = conductor.sources
        if query:
            found = sources.find_repositories(query, limit=REPOSITORY_SEARCH_LIMIT)
        else:
            ours = institution_repositories.ids(conductor.profile)
            found = sources.repositories([*ours, *(requirements.suggested if requirements else ())])
        return {
            "snapshot_ref": sources.re3data_export_ref(),
            "query": query,
            "suggested": not query,
            "repositories": [m.describe() for m in found],
        }

    def validate(self, project_id: str, *, acted_for: Principal, caused_by: str) -> dict[str, Any]:
        store: DepositSource = self._store
        validation, digest = check(store, project_id, acted_for=acted_for, caused_by=caused_by)
        return deposit.validation_view(validation, digest)

    def package(
        self, project_id: str, *, acted_for: Principal, caused_by: str
    ) -> tuple[Package, dict[str, Any]]:
        """The deposit package, built only if the project is valid, and the validation as the
        shell draws it. Raises `PackageRefusedError` when it is not valid."""
        store: DepositSource = self._store
        built = build_package(
            store,
            self.governance.conductor.store,
            project_id,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return built, self.validation_view(project_id, built.validation)

    def validation_view(self, project_id: str, validation: Validation) -> dict[str, Any]:
        store: ProjectRecord = self._store
        return deposit.validation_view(validation, deposit.last_report_digest(store, project_id))

    def package_content(self, project_id: str, digest: str) -> bytes | None:
        """A package the project log records as built, or None (a digest that is not one too)."""
        store: ProjectDeposits = self._store
        if not deposit.DIGEST.fullmatch(digest):
            return None
        return store.package(project_id, digest)

    def disclosure(self, project_id: str) -> Disclosure:
        store: ProjectDocuments = self._store
        return disclose(store, self.governance.conductor.store, project_id)

    # --- Depositing through an API (docs/specs/deposit.md) -----------------------------------

    def connection(self, project_id: str) -> deposit_api.Connection | None:
        """How the project's repository is deposited to, or None if it chose none."""
        store: DepositSource = self._store
        requirements = self.governance.requirements
        if requirements is None:
            return None
        return deposit_api.connection(
            store,
            project_id,
            requirements=requirements,
            offered=self.governance.conductor.profile.deposit_transports,
            transports=self.governance.transports,
            broker=self.governance.deposit_broker,
        )

    def deposits(self, project_id: str) -> list[dict[str, Any]]:
        """Each deposit approved in the project, oldest first, as the app shows it."""
        store: DepositSource = self._store
        return [deposit_api.summary(d) for d in deposit_api.deposits(store, project_id)]

    def deposit(
        self, project_id: str, digest: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Approve the deposit of a package, as `acted_for`, and make the draft; the deposit as
        the app shows it. Raises `DepositRefusedError` or `DepositInProgressError`."""
        store: DepositSource = self._store
        outcome = deposit_api.approve_and_deposit(
            store,
            project_id,
            digest,
            requirements=self._requirements(),
            offered=self.governance.conductor.profile.deposit_transports,
            transports=self.governance.transports,
            broker=self.governance.deposit_broker,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        (shown,) = [
            deposit_api.summary(d)
            for d in deposit_api.deposits(store, project_id)
            if d["approval"]["event_id"] == outcome["approval"]
        ]
        return shown
