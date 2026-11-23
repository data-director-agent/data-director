"""A project's documents, and the facts agents propose and people decide
(docs/specs/projects.md, docs/specs/drafting.md)."""

from __future__ import annotations

from typing import Any

from dd_app import documents
from dd_app.project_service._area import Area
from dd_harness.projects import Decision, FactVerdict
from dd_harness.storage import ProjectDocuments, ProjectFacts
from dd_sdk.contract.models import DraftAnswer, Principal


class Documents(Area):
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

    def request_revision(
        self,
        project_id: str,
        document_id: str,
        version: int,
        digest: str,
        instruction: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> tuple[str, str]:
        """Record `acted_for`'s request for changes to the latest version, and return the agent to
        revise it and the document's kind. Raises `NoDrafterError`, recording nothing, if no agent
        drafted the document."""
        store: ProjectDocuments = self._store
        agent_id, kind = documents.drafter(store, project_id, document_id)
        store.request_revision(
            project_id,
            document_id,
            version,
            digest,
            instruction,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return agent_id, kind

    def drafter_of_latest(self, project_id: str, document_id: str, version: int) -> tuple[str, str]:
        """The agent to draft `document_id` again from the project's answers, and the document's
        kind, once `version` is checked to be the latest. Records nothing: the run the
        conductor records is the request (docs/specs/drafting.md, invariant 10)."""
        store: ProjectDocuments = self._store
        return documents.drafter_of_latest(store, project_id, document_id, version)


class Facts(Area):
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
