"""What the app's routes may do with projects: the one way they reach the projects' logs.

Each method is one thing a route does, and answers with what the route then shows, read back
from the log. The harness decides and records (`dd_harness.projects`); this module holds the
app's own rules about a request, such as that a project is deleted only by someone who typed its
name, and wires the harness's pieces together, such as the pinned re3data export a repository
choice resolves against. Every method blocks, so a route calls it off the event loop.

Whom a change acts for is always the principal the authenticator names, never a request's body,
and `caused_by` is the request that caused it (docs/specs/projects.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dd_app import deposit, documents
from dd_app.governance import CREATED_BY_ROUTE, Governance
from dd_harness.deposit import Package, PackageRefusedError, Validation, build_package, check
from dd_harness.disclosure import Disclosure, disclose
from dd_harness.projects import (
    TITLE_BY_RESEARCHER,
    Decision,
    FactVerdict,
    ProjectError,
    UnknownProjectError,
)
from dd_harness.requirements import Requirements
from dd_harness.storage import (
    DepositSource,
    ProjectDeposits,
    ProjectDocuments,
    ProjectFacts,
    ProjectHoldings,
    ProjectLifecycle,
    ProjectProgress,
    ProjectRecord,
    ProjectRepository,
    ProjectResearchers,
    ProjectStorage,
)
from dd_sdk.contract.models import DraftAnswer, Principal

# The most repositories one search of the pinned re3data export answers with.
REPOSITORY_SEARCH_LIMIT = 20


class TitleMismatchError(ProjectError):
    """The name typed to delete a project is not its name."""


class RepositoriesUnavailableError(Exception):
    """This server has no repository requirement sets, so no repository can be chosen."""


@dataclass(frozen=True)  # noqa: PLR0904
class ProjectService:
    governance: Governance

    @property
    def _store(self) -> ProjectStorage:
        if self.governance.projects is None:
            raise UnknownProjectError("this server keeps no projects")
        return self.governance.projects

    @property
    def keeps_projects(self) -> bool:
        return self.governance.projects is not None

    @property
    def offers_repositories(self) -> bool:
        """Whether this server has repository requirement sets, so that one may be chosen."""
        return self.governance.requirements is not None

    # Lifecycle (docs/specs/projects.md, "Deletion and retention").

    def create(self, title: str | None, *, acted_for: Principal) -> dict[str, Any]:
        """A project of its own, with no conversation, as `GET /api/projects` lists it."""
        store: ProjectLifecycle = self._store
        project_id = store.create(acted_for=acted_for, caused_by=CREATED_BY_ROUTE, title=title)
        return {**store.summary(project_id), "conversations": []}

    def delete(
        self, project_id: str, typed: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Delete the project, which hides it and removes nothing, once the person has typed its
        name: its title, or its identifier while it has none. The check is here as well as on the
        page, so no client can skip it. Answers with its summary, whose `deleted` says until when
        it may be restored."""
        store: ProjectLifecycle = self._store
        if typed.strip() != (store.summary(project_id)["title"] or project_id):
            raise TitleMismatchError(
                "`title` is not the project's name. Type it exactly to delete the project."
            )
        store.delete(project_id, acted_for=acted_for, caused_by=caused_by)
        return store.summary(project_id)

    def restore(self, project_id: str, *, acted_for: Principal, caused_by: str) -> dict[str, Any]:
        store: ProjectLifecycle = self._store
        store.restore(project_id, acted_for=acted_for, caused_by=caused_by)
        return store.summary(project_id)

    def rename(
        self, project_id: str, title: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """A person's name for the project, which a model's never replaces."""
        store: ProjectLifecycle = self._store
        store.rename(
            project_id, title, source=TITLE_BY_RESEARCHER, acted_for=acted_for, caused_by=caused_by
        )
        return store.summary(project_id)

    # What the project holds of the researcher's files, and of the researcher.

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        store: ProjectHoldings = self._store
        return store.inventory(project_id)

    def add_inventory(
        self, project_id: str, inventory: dict[str, Any], *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """The project's latest inventory: a revision of the one it holds, or a new scan."""
        store = self._store
        store.add_inventory(project_id, inventory, acted_for=acted_for, caused_by=caused_by)
        held: dict[str, Any] = store.summary(project_id)["inventory"]
        return held

    def documentation(self, project_id: str) -> list[dict[str, Any]]:
        store: ProjectHoldings = self._store
        return store.documentation(project_id)

    def documentation_text(self, project_id: str, digest: str) -> str | None:
        store: ProjectHoldings = self._store
        return store.documentation_text(project_id, digest)

    def documentation_source(self, project_id: str, digest: str) -> tuple[bytes, str] | None:
        store: ProjectHoldings = self._store
        return store.documentation_source(project_id, digest)

    def researchers(self, project_id: str) -> list[dict[str, Any]]:
        store: ProjectResearchers = self._store
        return store.researchers(project_id) or []

    def keep_researcher(
        self, project_id: str, chosen: dict[str, Any], *, acted_for: Principal, caused_by: str
    ) -> list[dict[str, Any]]:
        store: ProjectResearchers = self._store
        store.add_researcher(project_id, chosen, acted_for=acted_for, caused_by=caused_by)
        return store.researchers(project_id) or []

    def withdraw_researcher(
        self, project_id: str, *, acted_for: Principal, caused_by: str
    ) -> list[dict[str, Any]]:
        store: ProjectResearchers = self._store
        store.withdraw_researcher(
            project_id, acted_for.principal_id, acted_for=acted_for, caused_by=caused_by
        )
        return store.researchers(project_id) or []

    # Where the project is (docs/specs/orchestration.md) and its intake (docs/specs/app.md).

    def progress(self, project_id: str) -> dict[str, Any]:
        store: ProjectProgress = self._store
        return store.progress(project_id)

    def choose_entry(
        self, project_id: str, entry: int, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.choose_entry(project_id, entry, acted_for=acted_for, caused_by=caused_by)
        return store.progress(project_id)

    def mark_step(
        self, project_id: str, step_id: str, mark: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.mark_step(project_id, step_id, mark, acted_for=acted_for, caused_by=caused_by)
        return store.progress(project_id)

    def intake(self, project_id: str) -> dict[str, Any]:
        store: ProjectProgress = self._store
        return store.intake(project_id)

    def answer_intake(
        self,
        project_id: str,
        question_id: str,
        values: list[str],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.answer_intake(
            project_id, question_id, values, acted_for=acted_for, caused_by=caused_by
        )
        return store.intake(project_id)

    def dismiss_intake(
        self, project_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.dismiss_intake(project_id, acted_for=acted_for, caused_by=caused_by)
        return store.intake(project_id)

    # Documents (docs/specs/projects.md, docs/specs/drafting.md).

    def documents(self, project_id: str) -> dict[str, Any]:
        store: ProjectDocuments = self._store
        return documents.view(store, project_id)

    def decide(
        self, project_id: str, decision: Decision, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectDocuments = self._store
        decided = store.decide(project_id, decision, acted_for=acted_for, caused_by=caused_by)
        return {**documents.view(store, project_id), "decided": decided.model_dump()}

    def answer(
        self,
        project_id: str,
        document_id: str,
        version: int,
        answers: list[DraftAnswer],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        store: ProjectDocuments = self._store
        answered = store.answer(
            project_id, document_id, version, answers, acted_for=acted_for, caused_by=caused_by
        )
        return {**documents.view(store, project_id), "answered": answered.model_dump()}

    # Facts agents propose and people decide (docs/specs/projects.md).

    def facts(self, project_id: str) -> dict[str, Any]:
        store: ProjectFacts = self._store
        return {
            "proposals": store.proposals(project_id),
            "decisions": store.decisions(project_id) or [],
        }

    def proposed_kind(self, project_id: str, proposal: str) -> str | None:
        """The kind of fact `proposal` proposed, or None if the project holds no such proposal."""
        store: ProjectFacts = self._store
        fact = store.proposal(project_id, proposal)
        return None if fact is None else str(fact["fact_kind"])

    def decide_fact(
        self,
        project_id: str,
        verdict: FactVerdict,
        *,
        proposal: str | None,
        fact: dict[str, Any] | None,
        reason: str | None,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        store: ProjectFacts = self._store
        decided = store.decide_fact(
            project_id,
            verdict,
            proposal=proposal,
            fact=fact,
            reason=reason,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return {**self.facts(project_id), "decided": decided}

    # Repository choice and deposit (docs/specs/deposit.md).

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        store: ProjectRepository = self._store
        return store.requirements(project_id)

    def choose_repository(
        self, project_id: str, re3data_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any] | None:
        """The researcher's choice, by its re3data identifier alone: its name and declared
        standards come from the pinned re3data export, resolved against the deployment's
        requirement sets. A change is a new choice, and the last one counts."""
        store, requirements = self._store, self._requirements()
        store.choose_repository(
            project_id,
            re3data_id,
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
        """Those the pinned re3data export holds that `query` names, or, without one, those the
        deployment suggests (its overrides, then `suggested.yaml`)."""
        sources, requirements = self.governance.conductor.sources, self.governance.requirements
        if query:
            found = sources.find_repositories(query, limit=REPOSITORY_SEARCH_LIMIT)
        else:
            found = sources.repositories(requirements.suggested if requirements else ())
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


__all__ = [
    "PackageRefusedError",
    "ProjectService",
    "RepositoriesUnavailableError",
    "TitleMismatchError",
]
