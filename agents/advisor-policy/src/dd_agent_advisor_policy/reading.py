"""Reading the policies' own text: which pages to read, fetching each, with its retrieval span,
before any model is called (docs/specs/grounding.md, G1), then having the extractor's model report
what each requires, and a sentence for the statement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple

from dd_agent_advisor_policy import assess
from dd_agent_advisor_policy.classes import (
    Actor,
    ObligationKind,
    PolicyReading,
    ReadingStatus,
    Strength,
)
from dd_agent_advisor_policy.extract import Extractor, NoExtractor
from dd_agent_advisor_policy.grounding import record_ref
from dd_agent_advisor_policy.policy_text import Pages, PolicyText, UnreadableError, readable_url
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import EvidenceItem, GroundingRef
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash
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


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def read_texts(
    matched: list[tuple[Actor, list[PolicyRecord]]],
    ctx: RunContext,
    *,
    off: bool,
    pages: Pages | None,
    extractor: Extractor,
) -> TextReadings:
    """Fetch and read each policy's own text: the page each matched record names, and each
    `policy_url` given. Every page is fetched, with its retrieval span, before any model is
    called (docs/specs/grounding.md, G1)."""
    out = TextReadings()
    wanted = reading_targets(matched)
    if not wanted:
        return out
    if off:
        out.note = " The policies' own text was not read: the deployment turns reading off."
        return out
    if pages is None or isinstance(extractor, NoExtractor):
        out.note = (
            " The policies' own text was not read: no model is configured to read it, so "
            "only FAIRsharing's curated records were."
        )
        return out
    reader = _Reader(extractor, ctx, out, pages.snapshot_ref().as_string(), datetime.now(UTC))
    unread: list[str] = []
    for fetched in fetch_pages(pages, wanted, ctx):
        record_refs = [record_ref(fetched.origin)] if fetched.origin is not None else []
        if fetched.page is not None:
            reader.read(fetched.actor, fetched.page, record_refs)
        elif record_refs:
            out.readings.append(unread_reading(fetched, record_refs))
        else:
            unread.append(f"{fetched.url} ({fetched.problem})")
    out.note = reading_note(out.readings, matched, unread, extractor.model_id)
    return out


@dataclass
class _Reader:
    """Has the extractor read each fetched page, adding its reading and evidence to `out`."""

    extractor: Extractor
    ctx: RunContext
    out: TextReadings
    where: str
    now: datetime

    def read(self, actor: Actor, page: PolicyText, record_refs: list[GroundingRef]) -> None:
        out = self.out
        reading = self.extractor.extract(actor, page, self.ctx, out.calls)
        out.calls = reading.calls or out.calls
        out.input_tokens += reading.usage.input_tokens or 0
        out.output_tokens += reading.usage.output_tokens or 0
        ref = text_ref(page)
        out.refs.append(ref)
        out.evidence.append(
            EvidenceItem(
                source_id=page.url,
                source_uri=page.url,
                retrieved_at=self.now,
                snapshot_ref=self.where,
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=DOCUMENT_CANONICALISATION,
                content_hash=ref.content_hash,
                content=page.document(),
            )
        )
        reasons = []
        if reading.why_not:
            reasons.append(f"The text was not read: {reading.why_not}.")
        if page.truncated:
            reasons.append("The text was long and only its first part was read.")
        out.readings.append(
            PolicyReading(
                actor=actor.name,
                role=actor.role,
                status=ReadingStatus.NOT_READ if reading.why_not else ReadingStatus.READ,
                stated=reading.checked.stated,
                dropped=reading.checked.dropped,
                reason=" ".join(reasons) or None,
                grounded_on=[ref, *record_refs],
            )
        )


def reading_note(
    readings: list[PolicyReading],
    matched: list[tuple[Actor, list[PolicyRecord]]],
    unread: list[str],
    model_id: str | None,
) -> str:
    """The statement's sentence on what reading the policies' own text found."""
    read = [r for r in readings if r.status == ReadingStatus.READ]
    note = _read_note(read, matched, model_id) if read else ""
    not_read = [r for r in readings if r.status != ReadingStatus.READ]
    if not_read:
        note += (
            f" The text of {plural(len(not_read), 'policy')} was not read; each reading says why."
        )
    if unread:
        note += " A page given for a policy could not be read: " + "; ".join(unread) + "."
    return note


def _read_note(
    read: list[PolicyReading],
    matched: list[tuple[Actor, list[PolicyRecord]]],
    model_id: str | None,
) -> str:
    stated = sum(len(r.stated) for r in read)
    note = (
        f" The policies' own text was read for {plural(len(read), 'policy')} by a model "
        f"({model_id}): {plural(stated, 'obligation')} found, each with "
        "the passage it comes from, which the agent has checked is in the text. A person "
        "should confirm each against the policy."
    )
    required = sorted(
        {
            o.value
            for r in read
            for o in r.stated
            if o.kind == ObligationKind.REPOSITORY and o.strength == Strength.REQUIRED
        }
    )
    if required:
        note += " Repositories the text says are required: " + "; ".join(required) + "."
    differ = differences(read, matched)
    if differ:
        note += (
            " The text and its FAIRsharing record state these differently: "
            + "; ".join(differ)
            + ". Both are shown; a person should decide."
        )
    return note


def differences(
    read: list[PolicyReading], matched: list[tuple[Actor, list[PolicyRecord]]]
) -> list[str]:
    """Where a policy's text states an obligation's strength differently from its record."""
    records = {r.source_id: r for _, found in matched for r in found}
    out: list[str] = []
    for reading in read:
        for ref in reading.grounded_on:
            record = records.get(ref.source_id)
            if record is not None:
                out += _differ(reading, record)
    return out


def _differ(reading: PolicyReading, record: PolicyRecord) -> list[str]:
    curated = {
        o.kind: o.strength for o in assess.obligations(record) if o.strength != Strength.UNSTATED
    }
    out: list[str] = []
    for kind in sorted({o.kind for o in reading.stated}):
        strengths = {o.strength for o in reading.stated if o.kind == kind}
        if kind in curated and curated[kind] not in strengths:
            out.append(
                f"{kind.value.replace('_', ' ')} for {reading.actor!r}: the record "
                f"says {curated[kind].value}, the text "
                f"{' and '.join(sorted(s.value for s in strengths))}"
            )
    return out
