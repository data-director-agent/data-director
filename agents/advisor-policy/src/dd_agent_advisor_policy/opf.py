"""Jisc Open Policy Finder: funder, publisher and journal open access policies, read live.

Open Policy Finder (https://openpolicyfinder.jisc.ac.uk) replaced Sherpa Romeo, Juliet and Fact
in 2024. It states what a funder requires of its outputs, including any data archiving
requirement, and where a version of an article may be deposited, after what embargo and under
which licence. The client is `dd_mcp_opf`, a separate member that speaks no Data Director
contract, and which is also an MCP server; this module makes each of its records a source the
agent cites, labelled `open-policy-finder:live:<date>`.

It is read live only, with a free key. Jisc licenses the data under CC BY-NC-ND 4.0, and the API
is for non-commercial use. No-derivatives rules out the projected registry a snapshot would be
built into, and Jisc states no rate limit, so there is no snapshot to fall back to: when the route
fails, the agent says so and carries on with FAIRsharing (docs/specs/dependencies.md).

Each record is projected to `OpfRecord`, hashed whole under `dd-json-document-v1` like a
FAIRsharing record. Numbers are kept as strings, since the A2A transport would turn them into
doubles and change the hash (records.py). Any failure to ask raises `RegistryUnavailable`; an
unknown identifier is None. Run `dd-mcp-opf check` with `OPEN_POLICY_FINDER_API_KEY` set to try
the route against a few known records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from dd_agent_advisor_policy.records import prompt_json
from dd_mcp_opf.client import ITEM_TYPES, ItemType, OpfUnavailableError
from dd_mcp_opf.client import OpenPolicyFinder as OpfClient
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.registry import RegistryUnavailable, SnapshotRef

__all__ = ["ITEM_TYPES", "OpenPolicyFinder", "OpfLink", "OpfRecord"]

PUBLIC_URL = "https://openpolicyfinder.jisc.ac.uk/{item_type}/{id}"
REGISTRY_LABEL = "open-policy-finder"
SEARCH_LIMIT = 10
# The most characters of one record's policy text a model is shown.
PROMPT_CHARS = 6000


class OpfLink(BaseModel):
    """A link from a journal's record to one of its publishers'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str | None = None
    relationship: str | None = None


class OpfRecord(BaseModel):
    """One Open Policy Finder record, as this agent keeps it
    (`dd_mcp_opf.client.record_from_item`, without its `page`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_type: ItemType
    id: str
    names: list[str] = Field(default_factory=list)
    acronyms: list[str] = Field(default_factory=list)
    country: str | None = None
    url: str | None = None
    issns: list[str] = Field(default_factory=list)
    publishers: list[OpfLink] = Field(default_factory=list)
    identifiers: list[Any] = Field(default_factory=list)
    # The policies as the record states them, numbers as strings.
    policies: list[Any] = Field(default_factory=list)

    # What every source record offers the agent (retrieve.SourceRecord).
    registry: ClassVar[str] = "Open Policy Finder"

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> OpfRecord:
        return cls.model_validate({k: v for k, v in record.items() if k != "page"})

    @property
    def source_id(self) -> str:
        return PUBLIC_URL.format(item_type=self.item_type, id=self.id)

    @property
    def source_uri(self) -> str:
        return self.source_id

    @property
    def name(self) -> str:
        return self.names[0] if self.names else f"{self.item_type} {self.id}"

    @property
    def label(self) -> str:
        return f"{self.name} (Open Policy Finder {self.item_type} {self.id})"

    @property
    def kind(self) -> str:
        """What the record is a policy of, in FAIRsharing's terms where they agree."""
        return {"publication": "journal", "publisher": "journal_publisher"}.get(
            self.item_type, self.item_type
        )

    def all_names(self) -> list[str]:
        return [n.casefold() for n in (*self.names, *self.acronyms)]

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)

    def prompt_text(self, limit: int = PROMPT_CHARS) -> str:
        return prompt_json(self.document(), limit)


class OpenPolicyFinder:
    """The live API, as the agent reads it. One instance serves concurrent runs: it keeps no
    per-run state."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        now: datetime | None = None,
        contact: str | None = None,
    ) -> None:
        self._client = OpfClient(api_key, client=client, contact=contact)
        self._now = now

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def search(self, item_type: ItemType, text: str, limit: int = SEARCH_LIMIT) -> list[OpfRecord]:
        """Records of `item_type` whose name (a journal's title) has the telling words of
        `text`."""
        try:
            found = self._client.search(item_type, text, limit)
        except OpfUnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None
        return [OpfRecord.from_record(r) for r in found]

    def fetch(self, item_type: ItemType, identifier: str) -> OpfRecord | None:
        """One record by its identifier (or, for a journal, an ISSN). None if there is none."""
        try:
            found = self._client.fetch(item_type, identifier)
        except OpfUnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None
        return OpfRecord.from_record(found) if found else None

    def journal_by_issn(self, issn: str) -> OpfRecord | None:
        return self.fetch("publication", issn)
