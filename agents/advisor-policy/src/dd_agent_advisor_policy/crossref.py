"""Crossref's journals API: which publisher a journal belongs to.

Most journals have no data policy of their own in FAIRsharing; they follow their publisher's
(#905). Crossref is the maintained source of the link from a journal to its publisher, so no
table of publishers is kept here:

- `GET https://api.crossref.org/journals/{issn}` reads one journal by ISSN;
- `GET https://api.crossref.org/journals?query=<title>&rows=<n>` searches by title.

Both need no account. Requests carry the project's User-Agent, which names no person; a
deployment may add its operators' contact address (`DD_REGISTRY_CONTACT`), which puts the
requests in Crossref's faster "polite" pool. Crossref's
metadata is CC0, but there is no pinned copy: the route is read live, and when it fails the
agent says so and carries on (docs/specs/dependencies.md).

Each journal is projected to `CrossrefJournal` and hashed whole under `dd-json-document-v1`.
Any transport failure, error status or unreadable answer raises `RegistryUnavailable`; an
unknown ISSN is None.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from dd_sdk.credentials import ConfigError
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.registry import RegistryUnavailable, SnapshotRef, pinned

API_BASE = "https://api.crossref.org/journals"
REGISTRY_LABEL = "crossref-journals"
TIMEOUT_S = 20.0
SEARCH_ROWS = 5
ISSN = re.compile(r"^\d{4}-?\d{3}[\dX]$")
CONTACT_SETTING = "DD_REGISTRY_CONTACT"
# One plain address: nothing that could end the User-Agent's comment or start another header.
ADDRESS = re.compile(r"[^\s@<>();,\"\\]+@[^\s@<>();,\"\\]+\.[^\s@<>();,\"\\]+")


def contact_from(env: Mapping[str, str]) -> str | None:
    """The operators' contact address `DD_REGISTRY_CONTACT` gives, or None when it is unset or
    blank. Anything but one plain address is a `ConfigError`."""
    value = (env.get(CONTACT_SETTING) or "").strip()
    if value and not ADDRESS.fullmatch(value):
        raise ConfigError(f"{CONTACT_SETTING}={value!r}: expected one e-mail address")
    return value or None


def normal_issn(value: str) -> str | None:
    """`value` as `NNNN-NNNC`, or None if it is not an ISSN."""
    text = value.strip().upper()
    if not ISSN.match(text):
        return None
    digits = text.replace("-", "")
    return f"{digits[:4]}-{digits[4:]}"


class CrossrefJournal(BaseModel):
    """A journal as Crossref records it: its title, ISSNs and publisher."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    publisher: str | None = None
    issns: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)

    registry: ClassVar[str] = "Crossref"

    @property
    def source_id(self) -> str:
        key = self.issns[0] if self.issns else self.title
        return f"{API_BASE}/{key}"

    @property
    def source_uri(self) -> str:
        return self.source_id

    @property
    def name(self) -> str:
        return self.title

    @property
    def label(self) -> str:
        issn = f", ISSN {self.issns[0]}" if self.issns else ""
        return f"{self.title} (Crossref{issn})"

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)

    def prompt_text(self, limit: int = 1000) -> str:
        text = (
            f"title: {self.title}; publisher: {self.publisher or '(not given)'}; "
            f"ISSNs: {', '.join(self.issns) or '(none)'}"
        )
        return text[:limit]


def from_message(message: dict[str, Any]) -> CrossrefJournal | None:
    title = message.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    issns = sorted(
        {n for n in (normal_issn(str(i)) for i in message.get("ISSN") or []) if n is not None}
    )
    subjects = sorted(
        {
            s["name"]
            for s in message.get("subjects") or []
            if isinstance(s, dict) and isinstance(s.get("name"), str)
        }
    )
    publisher = message.get("publisher")
    return CrossrefJournal(
        title=" ".join(title.split()),
        publisher=publisher.strip() if isinstance(publisher, str) and publisher.strip() else None,
        issns=issns,
        subjects=subjects,
    )


class CrossrefJournals:
    def __init__(
        self,
        client: httpx.Client | None = None,
        now: datetime | None = None,
        contact: str | None = None,
    ) -> None:
        self._client = client
        self._now = now
        self.user_agent = pinned.user_agent(
            "data-director-agent-advisor-policy", "data-director-advisor-policy", contact
        )

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": self.user_agent})
        return self._client

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def _get(self, url: str, params: dict[str, str] | None = None) -> Any:
        try:
            resp = self._http().get(url, params=params, headers={"User-Agent": self.user_agent})
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Crossref: {type(exc).__name__}") from None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RegistryUnavailable(f"Crossref: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise RegistryUnavailable("Crossref: an answer that is not JSON") from None
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict):
            raise RegistryUnavailable("Crossref: an answer with no message")
        return message

    def by_issn(self, issn: str) -> CrossrefJournal | None:
        wanted = normal_issn(issn)
        if wanted is None:
            return None
        message = self._get(f"{API_BASE}/{wanted}")
        return from_message(message) if message else None

    def search(self, title: str, rows: int = SEARCH_ROWS) -> list[CrossrefJournal]:
        message = self._get(API_BASE, {"query": title.strip(), "rows": str(rows)})
        items = (message or {}).get("items") or []
        found = [from_message(i) for i in items if isinstance(i, dict)]
        unique = {j.source_id: j for j in found if j is not None}
        return list(unique.values())
