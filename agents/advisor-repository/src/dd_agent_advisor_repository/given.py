"""What people in the project decided, read into the needs (docs/specs/projects.md, invariant 6).

In a project the conductor gives `RepositoryNeeds` the facts people decided
(`project_decisions`) and the repository the researcher chose (`project_repository`). A
person's decision takes precedence over what the caller wrote: each decided required repository
is mandated, whether or not the caller named it. The chosen repository is described only when
nothing else is asked (no mandate and nothing to search for), where the agent would otherwise
abstain; a caller that asks for a shortlist still gets one, so a researcher can reconsider.
Outside a project the caller's needs stand as sent.
"""

from __future__ import annotations

from dd_agent_advisor_repository import rank
from dd_agent_advisor_repository.classes import CandidateBasis, RepositoryNeeds, RepositoryRef
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_sdk.contract.facts import FactKind


def with_project(needs: RepositoryNeeds) -> tuple[RepositoryNeeds, str | None]:
    """The needs with each decided required repository mandated, and with the chosen
    repository to describe when nothing else is asked; and the re3data identifier of a
    repository described only because it was chosen, or None."""
    mandated = list(needs.mandated)
    for fact in needs.project_decisions:
        if fact.fact_kind == FactKind.REQUIRED_REPOSITORY and fact.fact_repository_name:
            decided = RepositoryRef(name=fact.fact_repository_name, re3data_id=fact.fact_re3data_id)
            if not any(_same(decided, ref) for ref in mandated):
                mandated.append(decided)
    only_chosen = None
    chosen = needs.project_repository
    if chosen is not None and not mandated and not rank.queries(needs):
        mandated.append(
            RepositoryRef(name=chosen.chosen_repository_name, re3data_id=chosen.chosen_re3data_id)
        )
        only_chosen = chosen.chosen_re3data_id
    return needs.model_copy(update={"mandated": mandated}), only_chosen


def basis(record: Re3dataRecord, only_chosen: str | None) -> CandidateBasis:
    """Why a named repository is described: chosen by the researcher, or mandated."""
    if record.re3data_id == only_chosen:
        return CandidateBasis.CHOSEN
    return CandidateBasis.MANDATED


def _same(a: RepositoryRef, b: RepositoryRef) -> bool:
    if a.re3data_id and b.re3data_id:
        return a.re3data_id == b.re3data_id
    return a.name.casefold() == b.name.casefold()
