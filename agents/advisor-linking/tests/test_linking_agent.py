"""advisor.linking through the conductor: the Linking Adviser mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_linking
from dd_agent_advisor_linking.agent import LinkingAdviser, orcid_checksum_ok
from dd_agent_advisor_linking.classes import LinkCandidates, RelatedIdentifiers
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_linking.__file__).parent / "schema" / "linking.yaml"


def sample() -> LinkCandidates:
    return LinkCandidates.model_validate(
        json.loads((SAMPLES / "link-candidates.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_recognises_checks_and_normalises_identifiers(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, LinkingAdviser())
    env = conductor.invoke(request("advisor.linking", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(RelatedIdentifiers)
    assert [
        (link.scheme, link.normalised, link.relation, link.valid) for link in payload.links
    ] == [
        ("doi", "https://doi.org/10.15497/RDA00157", "IsSupplementTo", True),
        ("orcid", "https://orcid.org/0000-0002-1825-0097", None, True),
        ("orcid", None, None, False),
        ("ror", "https://ror.org/05krs5044", None, True),
        ("unknown", None, None, False),
    ]
    assert "checksum" in payload.links[2].message
    assert any("resolved" in limitation for limitation in payload.limitations)
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_no_identifiers_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, LinkingAdviser()).invoke(
        request("advisor.linking", LinkCandidates(identifiers=["  "])), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_a_grant_number_is_taken_only_when_nothing_else_fits(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, LinkingAdviser()).invoke(
        request("advisor.linking", LinkCandidates(identifiers=["EP/T012345/1", "grant two"])),
        acting_for=TEST_PRINCIPAL,
    )
    payload = env.payload_as(RelatedIdentifiers)
    assert [(link.scheme, link.normalised) for link in payload.links] == [
        ("grant", None),
        ("unknown", None),
    ]


def test_the_orcid_checksum_follows_iso_7064() -> None:
    assert orcid_checksum_ok("0000-0002-1825-0097")
    assert orcid_checksum_ok("0000-0002-1694-233X")
    assert not orcid_checksum_ok("0000-0002-1825-0098")


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(LinkingAdviser.spec)
    assert entry["title"] == "Linking Adviser"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["deposit.links", "post.links"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
