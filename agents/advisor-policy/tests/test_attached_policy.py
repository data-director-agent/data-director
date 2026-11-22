"""A policy or award letter the researcher attached, read as a policy's own text (#1326): with no
address and no registry record, through the conductor, and in a project under the profile's rule
for sending document text to a hosted model."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dd_agent_advisor_policy import attached
from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    ObligationKind,
    PolicyChecks,
    PolicyContext,
    ReadingStatus,
)
from dd_agent_advisor_policy.extract import Extraction, ModelExtractor, Read, found
from dd_agent_advisor_policy.search import Sources
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.facts import ProjectDocument
from dd_sdk.contract.models import Envelope, OutcomeStatus
from dd_sdk.evidence import verify
from dd_sdk.model import declared
from dd_sdk.registry import Query, SnapshotRef
from dd_sdk.testing import FakeModel

POLICY = (
    "University of Testing research data policy.\n\n"
    "Researchers must deposit the data underpinning their publications in the University "
    "repository, ORDA, within three months of publication.\n"
)
TESTING = Actor(role=ActorRole.INSTITUTION, name="University of Testing")
SRC = Actor(role=ActorRole.FUNDER, name="Social Research Council")
DEPOSIT = Read(
    kind="repository",
    strength="required",
    value="ORDA",
    quote="must deposit the data underpinning their publications in the University repository",
)


def document(text: str = POLICY, name: str = "data-policy.md") -> ProjectDocument:
    return ProjectDocument(
        documentation_name=name,
        documentation_digest=hashlib.sha256(text.encode()).hexdigest(),
        documentation_media_type="text/markdown",
        documentation_size=len(text.encode()),
        documentation_added_at=datetime(2026, 11, 21, tzinfo=UTC),
        documentation_text=text,
    )


class NoPolicies:
    """FAIRsharing with no record of any policy."""

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-fairsharing-policy")

    def search(self, query: Query) -> list[object]:
        return []

    def fetch(self, fairsharing_id: str) -> None:
        return None


def advisor(model: FakeModel) -> PolicyAgent:
    """Built as the factory builds it with a model, and no web to fetch pages from."""
    agent = PolicyAgent(Sources(NoPolicies()), extractor=ModelExtractor(model))  # type: ignore[arg-type]
    agent.spec = replace(agent.spec, models=(declared(model),))
    return agent


def reads(*found: Read, hosting: str = "local") -> FakeModel:
    return FakeModel(Extraction(obligations=list(found)).model_dump_json(), hosting=hosting)  # type: ignore[arg-type]


# --- which actor a document is read for -------------------------------------------------------


def test_a_document_is_read_for_the_actor_it_names() -> None:
    letter = document("Award letter from the Social Research Council.", "award.pdf")
    targets = attached.targets([document(), letter], [TESTING, SRC])
    assert [(a.name, t.name) for a, t in targets.pairs] == [
        (TESTING.name, "data-policy.md"),
        (SRC.name, "award.pdf"),
    ]
    assert targets.unmatched == []


def test_a_document_naming_no_actor_is_read_for_the_only_one_or_not_at_all() -> None:
    anonymous = document("Deposit your data.", "notes.md")
    assert [a.name for a, _ in attached.targets([anonymous], [SRC]).pairs] == [SRC.name]
    either = attached.targets([anonymous], [TESTING, SRC])
    assert either.pairs == [] and either.unmatched == ["notes.md"]


# --- through the conductor --------------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_an_attached_policy_with_no_address_is_read_and_cited(runs_dir: Path) -> None:
    model = reads(DEPOSIT)
    given = document()
    context = PolicyContext(actors=[TESTING], project_documents=[given])
    env = make_conductor(runs_dir, advisor(model)).invoke(
        request("advisor.policy", context), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [reading] = env.payload_as(PolicyChecks).readings
    assert reading.status == ReadingStatus.READ and reading.actor == TESTING.name
    assert [(o.kind, o.value) for o in reading.stated] == [(ObligationKind.REPOSITORY, "ORDA")]
    # Cited as evidence of its own, by its digest, with the text the quote is found in.
    source = f"{attached.SOURCE_PREFIX}{given.documentation_digest}"
    assert [g.source_id for g in reading.grounded_on] == [source]
    [cited] = [e for e in env.evidence if e.source_id == source]
    assert cited.content is not None and cited.source_uri is None
    assert cited.content["name"] == given.documentation_name
    assert cited.content["sha256"] == given.documentation_digest
    assert verify(cited.content, cited.canonicalisation, cited.content_hash)
    assert found(reading.stated[0].quote, cited.content["text"])
    assert given.documentation_name in env.outcome.statement
    assert DEPOSIT.quote in str(model.sent[0].messages)


def test_without_a_document_nothing_is_read(runs_dir: Path) -> None:
    model = reads(DEPOSIT)
    env = make_conductor(runs_dir, advisor(model)).invoke(
        request("advisor.policy", PolicyContext(actors=[TESTING])), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status != OutcomeStatus.FAILED
    assert model.sent == []


def test_it_says_which_agents_read_an_attachment() -> None:
    assert PolicyAgent(Sources(NoPolicies())).spec.reads_attached  # type: ignore[arg-type]


# --- in a project -----------------------------------------------------------------------------


def in_project(runs_dir: Path, tmp_path: Path, model: FakeModel) -> tuple[Conductor, str]:
    conductor = make_conductor(runs_dir, advisor(model))
    projects = ProjectStore(tmp_path / "projects")
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.add_documentation(
        project, "data-policy.md", "text/markdown", POLICY, acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    return conductor, conversation


def ask(conductor: Conductor, conversation: str) -> Envelope:
    req = request("advisor.policy", PolicyContext(actors=[TESTING]))
    return conductor.invoke(
        req.model_copy(update={"conversation_id": conversation}), acting_for=TEST_PRINCIPAL
    )


def test_in_a_project_the_conductor_gives_the_attached_policy(
    runs_dir: Path, tmp_path: Path
) -> None:
    model = reads(DEPOSIT, hosting="local")
    conductor, conversation = in_project(runs_dir, tmp_path, model)
    env = ask(conductor, conversation)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [reading] = env.payload_as(PolicyChecks).readings
    assert reading.status == ReadingStatus.READ
    assert DEPOSIT.quote in str(model.sent[0].messages)


def test_a_hosted_model_is_not_given_the_attached_policy_by_default(
    runs_dir: Path, tmp_path: Path
) -> None:
    """The text is `documentation`, which the default `hosted_models` keeps from a hosted model."""
    model = reads(DEPOSIT, hosting="hosted")
    conductor, conversation = in_project(runs_dir, tmp_path, model)
    env = ask(conductor, conversation)
    assert env.outcome.status != OutcomeStatus.FAILED
    assert model.sent == []
