"""The Directory of Open Access Journals: an open access journal's terms, with no API key (#1517).

DOAJ says, for each journal it lists, which licences it publishes under, whether authors keep
copyright, whether it has a deposit (self-archiving) policy and where that is recorded, how it is
preserved and what it charges, and who publishes it. The client is `dd_mcp_doaj`, a separate
member that speaks no Data Director contract; this module makes each of its records a source the
agent cites, labelled `doaj-journals:live:<date>`.

DOAJ waives its rights in the metadata under CC0, but there is no pinned copy: the route is read
live, and when it fails the agent says so and carries on (docs/specs/dependencies.md). DOAJ lists
open access journals only, so a journal it does not list says nothing about that journal.

Each record is hashed whole under `dd-json-document-v1` and cited by its DOAJ page. Any failure to
ask DOAJ raises `RegistryUnavailable`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from dd_agent_advisor_policy.records import prompt_json
from dd_mcp_doaj.journals import Doaj, DoajUnavailableError
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.registry import RegistryUnavailable, SnapshotRef

REGISTRY_LABEL = "doaj-journals"
PROMPT_CHARS = 3000


class DoajJournal(BaseModel):
    """One journal as DOAJ records it (`dd_mcp_doaj.journals.journal_record`)."""

    model_config = ConfigDict(frozen=True)

    record: dict[str, Any]

    registry: ClassVar[str] = "DOAJ"

    @property
    def source_id(self) -> str:
        return str(self.record["url"])

    @property
    def source_uri(self) -> str:
        return self.source_id

    @property
    def name(self) -> str:
        return str(self.record["title"])

    @property
    def title(self) -> str:
        return self.name

    @property
    def kind(self) -> str:
        """What the record is a policy of, in FAIRsharing's terms."""
        return "journal"

    @property
    def titles(self) -> list[str]:
        return [t for t in (self.record["title"], self.record.get("alternative_title")) if t]

    @property
    def publisher(self) -> str | None:
        value = self.record.get("publisher")
        return str(value) if value else None

    @property
    def issns(self) -> list[str]:
        return [i for i in (self.record.get("eissn"), self.record.get("pissn")) if i]

    @property
    def label(self) -> str:
        issn = f", ISSN {self.issns[0]}" if self.issns else ""
        return f"{self.name} (DOAJ{issn})"

    def document(self) -> dict[str, Any]:
        return dict(self.record)

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)

    def prompt_text(self, limit: int = PROMPT_CHARS) -> str:
        return prompt_json(self.document(), limit)


class DoajJournals:
    """DOAJ's live API, as the agent reads it. One instance serves concurrent runs."""

    def __init__(self, client: Doaj | None = None, now: datetime | None = None) -> None:
        self._client = client or Doaj()
        self._now = now

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def by_issn(self, issn: str) -> DoajJournal | None:
        try:
            found = self._client.by_issn(issn)
        except DoajUnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None
        return DoajJournal(record=found) if found else None

    def search(self, title: str) -> list[DoajJournal]:
        try:
            found = self._client.search(title)
        except DoajUnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None
        return [DoajJournal(record=r) for r in found]
