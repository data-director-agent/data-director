"""What people in the project decided, read into the needs (docs/specs/projects.md, invariant 6).

In a project the conductor gives `RepositoryNeeds` the facts people decided
(`project_decisions`) and the repository the researcher chose (`project_repository`). A
person's decision takes precedence over what the caller wrote: each decided required repository
is mandated, whether or not the caller named it. Each repository a confirmed sharing commitment of
the data management plan names is described beside the shortlist, as one the plan names: a plan's
choice is not a mandate (#1233). The chosen repository is described only when nothing else is
asked (no mandate, nothing asked about or named by the plan, nothing to search for), where the
agent would otherwise abstain; a caller that asks for a shortlist still gets one, so a researcher
can reconsider. When the needs give no kinds of data, they are taken from the project's inventory
(`kinds.py`, #1560).
Outside a project the caller's needs stand as sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dd_agent_advisor_repository import kinds, rank
from dd_agent_advisor_repository.classes import CandidateBasis, RepositoryNeeds, RepositoryRef
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_sdk.contract.facts import FactKind


@dataclass(frozen=True)
class Given:
    """The needs with the project's decisions read in; the repositories the plan names, to
    describe beside the shortlist; and the re3data identifier of a repository described only
    because it was chosen, or None; and the kinds of data taken from the inventory, if any."""

    needs: RepositoryNeeds
    in_plan: list[RepositoryRef] = field(default_factory=list)
    only_chosen: str | None = None
    from_inventory: kinds.FromInventory | None = None


def with_project(needs: RepositoryNeeds) -> Given:
    """The needs with each decided required repository mandated, the repositories confirmed
    plan commitments name, the chosen repository to describe when nothing else is asked, and the
    kinds of data from the inventory when the needs give none."""
    from_inventory = None
    if not needs.data_kinds and needs.project_file_inventory is not None:
        from_inventory = kinds.from_inventory(needs.project_file_inventory)
        needs = needs.model_copy(update={"data_kinds": from_inventory.kinds})
    mandated = list(needs.mandated)
    in_plan: list[RepositoryRef] = []
    for fact in needs.project_decisions:
        if fact.fact_kind == FactKind.REQUIRED_REPOSITORY and fact.fact_repository_name:
            decided = RepositoryRef(name=fact.fact_repository_name, re3data_id=fact.fact_re3data_id)
            if not any(_same(decided, ref) for ref in mandated):
                mandated.append(decided)
        elif fact.fact_kind == FactKind.SHARING_COMMITMENT and fact.commitment_repository:
            # A plan that commits one output to several repositories gives a commitment for each.
            planned = RepositoryRef(name=fact.commitment_repository)
            if not any(_same(planned, ref) for ref in in_plan):
                in_plan.append(planned)
    # A repository the plan names that is also mandated is described as mandated.
    in_plan = [ref for ref in in_plan if not any(_same(ref, m) for m in mandated)]
    only_chosen = None
    chosen = needs.project_repository
    if chosen is not None and not (mandated or in_plan or needs.asked_about or rank.queries(needs)):
        mandated.append(
            RepositoryRef(
                name=chosen.chosen_repository_name,
                re3data_id=chosen.chosen_re3data_id,
                repository_id=chosen.chosen_repository_id,
            )
        )
        only_chosen = chosen.chosen_repository_id
    return Given(
        needs.model_copy(update={"mandated": mandated}), in_plan, only_chosen, from_inventory
    )


def basis(record: Re3dataRecord, only_chosen: str | None) -> CandidateBasis:
    """Why a named repository is described: chosen by the researcher, or mandated."""
    if record.identifier == only_chosen:
        return CandidateBasis.CHOSEN
    return CandidateBasis.MANDATED


def _same(a: RepositoryRef, b: RepositoryRef) -> bool:
    if a.identifier and b.identifier:
        return a.identifier == b.identifier
    return a.name.casefold() == b.name.casefold()
