"""The repositories the deployment's profile names as its institution's, laid over the registries.

The conductor gives each as an `InstitutionRepository` (`RepositoryNeeds.institution_repositories`,
`GivenInstitutionRepositories`): a registry's identifier and what the deployment vouches for that
no registry holds, such as its access options, licences, or that it charges no fee. The deployment
knows its own repository better than the registry, as a steward's requirement override does
(docs/specs/deposit.md, invariant 5), so what it vouches for stands over the registry's silence.

A repository so named is its institution's for a researcher of that institution even when the
registry names another operator, such as a consortium or a platform. Its record keeps citing the
registry; what the deployment vouches for is cited as a second evidence item, under the profile's
reference, which the harness resolves against the profile it loaded (docs/specs/grounding.md).
"""

from __future__ import annotations

from typing import Any

from dd_agent_advisor_repository import assess
from dd_agent_advisor_repository.classes import Affiliation
from dd_agent_advisor_repository.records import Institution, bare_ror
from dd_agent_advisor_repository.retrieve import Repositories
from dd_sdk.contract.models import InstitutionRepository
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.registry import Hit, Query, SnapshotRef

# The evidence identifier of what the profile vouches for about one repository.
SOURCE_PREFIX = "institution:"


def source_id(entry: InstitutionRepository) -> str:
    return f"{SOURCE_PREFIX}{entry.repository_id}"


def document(entry: InstitutionRepository) -> dict[str, Any]:
    """What the profile vouches for, as hashed and shown: the entry as the conductor gave it."""
    return entry.model_dump(mode="json")


class Vouched:
    """A registry's record with what the profile vouches for laid over it. Every other name is
    the record's own, so assessing and ranking it needs nothing new."""

    def __init__(self, record: Any, entry: InstitutionRepository) -> None:
        self.record = record
        self.entry = entry

    def __getattr__(self, name: str) -> Any:
        return getattr(self.record, name)

    @property
    def data_access_types(self) -> list[str]:
        return sorted(self.entry.data_access_types) or list(self.record.data_access_types)

    @property
    def data_licences(self) -> list[str]:
        return sorted(self.entry.data_licences) or list(self.record.data_licences)

    @property
    def fee_vouched(self) -> bool | None:
        return self.entry.fee_required

    @property
    def institutions(self) -> list[Institution]:
        """The registry's operators, and the institution the profile names, where it names
        one: the repository is theirs whoever registered it."""
        own = list(self.record.institutions)
        if self.entry.institution_name:
            ror = bare_ror(self.entry.institution_ror) if self.entry.institution_ror else None
            own.append(Institution(name=self.entry.institution_name, ror=ror))
        return own

    def vouched_hash(self) -> str:
        return content_hash(document(self.entry), DOCUMENT_CANONICALISATION)


class WithInstitution:
    """The registries, with each record the profile names returned as `Vouched`, and those
    records among the researcher's institution's own when the affiliation matches."""

    def __init__(self, source: Repositories, entries: list[InstitutionRepository]) -> None:
        self.source = source
        self.entries = {e.repository_id: e for e in entries}

    def _vouched(self, record: Any) -> Any:
        if record is None or isinstance(record, Vouched):
            return record
        entry = self.entries.get(record.identifier)
        return Vouched(record, entry) if entry is not None else record

    def snapshot_ref(self) -> SnapshotRef:
        return self.source.snapshot_ref()

    def snapshot_of(self, record: Any) -> SnapshotRef:
        return self.source.snapshot_of(record.record if isinstance(record, Vouched) else record)

    def credit(self) -> str:
        return self.source.credit()

    def search(self, query: Query) -> list[Hit[Any]]:
        return [
            Hit(record=self._vouched(h.record), lexical_score=h.lexical_score)
            for h in self.source.search(query)
        ]

    def fetch(self, repository_id: str) -> Any:
        return self._vouched(self.source.fetch(repository_id))

    def subjects(self) -> dict[str, str]:
        return self.source.subjects()

    def with_subject(self, code: str) -> list[Any]:
        return [self._vouched(r) for r in self.source.with_subject(code)]

    def find(self, name: str) -> list[Any]:
        return [self._vouched(r) for r in self.source.find(name)]

    def institutional(self, affiliation: Affiliation | None) -> list[Any]:
        """The registries' records of the researcher's institution, and every record the profile
        names whose institution, as the profile or the registry gives it, is the researcher's."""
        found = {r.identifier: self._vouched(r) for r in self.source.institutional(affiliation)}
        for repository_id in sorted(self.entries):
            if repository_id in found:
                continue
            record = self.fetch(repository_id)
            if record is not None and assess.affiliated(record, affiliation) is not None:
                found[repository_id] = record
        return list(found.values())


def wrap(source: Repositories, entries: list[InstitutionRepository]) -> Repositories:
    """`source`, with the profile's repositories laid over it; itself when the profile names none."""
    return WithInstitution(source, entries) if entries else source  # type: ignore[return-value]
