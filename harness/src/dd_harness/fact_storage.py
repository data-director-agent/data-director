"""What the harness asks of a store for a project's facts: what check agents propose and people
decide (`dd_harness.projects.facts`, docs/specs/projects.md). `dd_harness.storage` composes it
into `ProjectStorage` with the other areas of the project rules; `decide_fact` is a change checked
against the log, in the project's exclusive section, as `ProjectStorage` guarantee 2 says."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from dd_harness.projects.facts import FactVerdict
from dd_sdk.contract.models import Principal


class ProjectFacts(Protocol):
    """The facts check agents propose and people decide (`dd_harness.projects.facts`)."""

    def propose_facts(
        self,
        project_id: str,
        facts: Iterable[Mapping[str, Any]],
        *,
        agent_id: str,
        acted_for: Principal,
        caused_by: str,
    ) -> list[str]:
        """Record a run's proposed `ProjectFact`s; returns the proposals' identifiers."""
        ...

    def decide_fact(
        self,
        project_id: str,
        verdict: FactVerdict,
        *,
        proposal: str | None = None,
        fact: Mapping[str, Any] | None = None,
        reason: str | None = None,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any] | None:
        """Record a person's decision on a proposal, or a fact they state; returns the fact that
        now stands, or None after a rejection."""
        ...

    def decisions(self, project_id: str) -> list[dict[str, Any]] | None:
        """The facts that stand, the last decision on each kind and subject; None while none."""
        ...

    def proposal(self, project_id: str, proposal: str) -> dict[str, Any] | None:
        """The fact a proposal proposed, decided or not; None if the project holds none."""
        ...

    def proposals(self, project_id: str) -> list[dict[str, Any]]:
        """The proposals no decision on their kind and subject has followed."""
        ...
