"""Reading the policies' own text as one step (`reading.read_texts`): when it is not done and the
statement says why, a page that cannot be fetched, a page read, and where a text and its
FAIRsharing record differ. The web and the model are fakes."""

from __future__ import annotations

from dd_agent_advisor_policy import reading
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    ObligationKind,
    PolicyReading,
    ReadingStatus,
    StatedObligation,
    Strength,
)
from dd_agent_advisor_policy.extract import Checked, Extractor, NoExtractor, Reading
from dd_agent_advisor_policy.policy_text import PolicyText
from dd_agent_advisor_policy.records import Clause, PolicyRecord
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import GroundingRef
from dd_sdk.prompts import ModelCallLog
from dd_sdk.registry import RegistryUnavailable, SnapshotRef
from dd_sdk.tracing import make_tracing

PAGE = "https://funder.example/data-policy"
GIVEN = "https://funder.example/given-policy"
RECORD = PolicyRecord(
    fairsharing_id="FAIRsharing.test-funder",
    name="Social Research Council data policy",
    policy_type="funder",
    homepage=PAGE,
    clauses={"sharing_data": Clause(values={"mandated_data_sharing": "required"})},
)
SRC = Actor(role=ActorRole.FUNDER, name="Social Research Council")
DEPOSIT = StatedObligation(
    kind=ObligationKind.DEPOSIT,
    strength=Strength.RECOMMENDED,
    value="deposit",
    quote="Grant holders should offer their data for deposit.",
)


def ctx() -> RunContext:
    return RunContext(tracer=make_tracing(service_name="test").tracer, input_ref="", input_hash="")


class Pages:
    """Policy pages, every one of which can be fetched unless the web is down."""

    def __init__(self, down: bool = False) -> None:
        self.down = down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-pages")

    def fetch(self, url: str) -> PolicyText:
        if self.down:
            raise RegistryUnavailable("the web is down")
        return PolicyText(url=url, media_type="text/html", sha256="0" * 64, text=DEPOSIT.quote)


class ReadsOne:
    """A model that reads one obligation in every text."""

    model_id: str | None = "fake-extractor"

    def extract(
        self, actor: Actor, text: PolicyText, ctx: RunContext, calls: ModelCallLog | None
    ) -> Reading:
        return Reading(checked=Checked(stated=[DEPOSIT]))


def read(
    matched: list[tuple[Actor, list[PolicyRecord]]],
    *,
    off: bool = False,
    pages: Pages | None = None,
    extractor: Extractor | None = None,
) -> reading.TextReadings:
    return reading.read_texts(
        matched,
        ctx(),
        off=off,
        pages=pages if pages is not None else Pages(),
        extractor=extractor if extractor is not None else ReadsOne(),
    )


def test_nothing_is_read_or_said_when_no_policy_names_a_page() -> None:
    record = RECORD.model_copy(update={"homepage": None})
    out = read([(SRC, [record])])
    assert out.readings == [] and out.evidence == [] and out.note == ""


def test_the_statement_says_why_the_text_was_not_read() -> None:
    for out in (
        read([(SRC, [RECORD])], off=True),
        read([(SRC, [RECORD])], extractor=NoExtractor()),
    ):
        assert out.readings == [] and out.evidence == [] and out.calls is None
        assert out.note


def test_a_page_that_cannot_be_fetched_is_a_reading_grounded_on_its_record() -> None:
    out = read([(SRC, [RECORD])], pages=Pages(down=True))
    [unread] = out.readings
    assert unread.status == ReadingStatus.NOT_READ
    assert [g.source_id for g in unread.grounded_on] == [RECORD.source_id]
    assert out.evidence == [] and out.note


def test_a_page_given_that_cannot_be_fetched_is_noted() -> None:
    given = SRC.model_copy(update={"policy_url": GIVEN})
    record = RECORD.model_copy(update={"homepage": None})
    out = read([(given, [record])], pages=Pages(down=True))
    assert out.readings == [] and out.evidence == []
    assert GIVEN in out.note


def test_a_page_read_is_evidence_and_its_reading_cites_the_text_and_the_record() -> None:
    out = read([(SRC, [RECORD])])
    [page] = out.readings
    assert page.status == ReadingStatus.READ and page.stated == [DEPOSIT]
    assert [g.source_id for g in page.grounded_on] == [PAGE, RECORD.source_id]
    assert [e.source_id for e in out.evidence] == [PAGE]
    assert [r.source_id for r in out.refs] == [PAGE]


def test_a_text_that_states_an_obligation_differently_from_its_record_is_flagged() -> None:
    stated = PolicyReading(
        actor=SRC.name,
        role=SRC.role,
        status=ReadingStatus.READ,
        stated=[DEPOSIT],
        grounded_on=[
            GroundingRef(source_id=PAGE, content_hash="0" * 64),
            GroundingRef(source_id=RECORD.source_id, content_hash=RECORD.content_hash()),
        ],
    )
    assert len(reading.differences([stated], [(SRC, [RECORD])])) == 1
    agreeing = stated.model_copy(
        update={"stated": [DEPOSIT.model_copy(update={"strength": Strength.REQUIRED})]}
    )
    assert reading.differences([agreeing], [(SRC, [RECORD])]) == []
    assert reading.differences([stated], []) == []
