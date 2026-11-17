"""Reading the policies' own text (`agent.PolicyAgent._read_texts`): which pages to read, and
fetching each, with its retrieval span, before any model is called (docs/specs/grounding.md, G1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from dd_agent_advisor_policy.classes import Actor, PolicyReading, ReadingStatus
from dd_agent_advisor_policy.policy_text import Pages, PolicyText, UnreadableError, readable_url
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import EvidenceItem, GroundingRef
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.prompts import ModelCallLog
from dd_sdk.registry import RegistryUnavailable
from dd_sdk.tracing import retrieval_span


def text_hash(text: PolicyText) -> str:
    return content_hash(text.document(), DOCUMENT_CANONICALISATION)


def text_ref(text: PolicyText) -> GroundingRef:
    return GroundingRef(source_id=text.url, content_hash=text_hash(text))


@dataclass
class TextReadings:
    """What reading the policies' own text gave: the readings, the evidence and references they
    rest on, the tokens and calls spent, and a sentence for the statement."""

    readings: list[PolicyReading] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    refs: list[GroundingRef] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    calls: ModelCallLog | None = None
    note: str = ""


class Fetched(NamedTuple):
    """One page fetched for an actor, from the record that names it (None for a `policy_url`
    given), or why it could not be."""

    url: str
    actor: Actor
    origin: SourceRecord | None
    page: PolicyText | None
    problem: str | None


def reading_targets(
    matched: list[tuple[Actor, list[PolicyRecord]]],
) -> dict[str, tuple[Actor, SourceRecord | None]]:
    """The pages to read: the page each matched record names, then each `policy_url` given."""
    out: dict[str, tuple[Actor, SourceRecord | None]] = {}
    for actor, found in matched:
        for record in found:
            url = readable_url(record.homepage)
            if url:
                out.setdefault(url, (actor, record))
    for actor, _ in matched:
        url = readable_url(actor.policy_url)
        if url:
            out.setdefault(url, (actor, None))
    return out


def fetch_pages(
    pages: Pages, wanted: dict[str, tuple[Actor, SourceRecord | None]], ctx: RunContext
) -> list[Fetched]:
    """Fetch every page wanted, each with its retrieval span."""
    fetched: list[Fetched] = []
    for url, (actor, source) in wanted.items():
        try:
            text = pages.fetch(url)
        except RegistryUnavailable as exc:
            fetched.append(Fetched(url, actor, source, None, f"it could not be fetched: {exc}"))
            continue
        except UnreadableError as exc:
            fetched.append(Fetched(url, actor, source, None, f"unreadable: {exc}"))
            continue
        with retrieval_span(ctx.tracer, url, text_hash(text)):
            pass
        fetched.append(Fetched(url, actor, source, text, None))
    return fetched


def unread_reading(item: Fetched, record_refs: list[GroundingRef]) -> PolicyReading:
    """The reading of a page that could not be fetched or read, grounded on its record."""
    return PolicyReading(
        actor=item.actor.name,
        role=item.actor.role,
        status=(
            ReadingStatus.UNREADABLE
            if (item.problem or "").startswith("unreadable")
            else ReadingStatus.NOT_READ
        ),
        reason=f"The policy's page {item.url}: {item.problem}.",
        grounded_on=record_refs,
    )
