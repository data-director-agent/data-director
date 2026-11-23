"""Repositories re3data does not list (#1342): the profile's `institution_repositories`, the
DataCite snapshot beside the re3data export, and a choice recorded by either registry's
identifier (docs/specs/deposit.md, docs/specs/policy-and-identity.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from requirement_sets import (
    DATACITE_RECORDS,
    DATACITE_SNAPSHOT,
    DURHAM,
    ORDA,
    override,
    registry,
    standard,
    write,
)

from dd_harness import agent_slots, institution_repositories
from dd_harness.policy import PolicyError, Profile
from dd_harness.projects import REPOSITORY_CHOSEN, ProjectStore
from dd_harness.requirements import RequirementsError, load_requirements
from dd_harness.sources import Sources, check
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL
from dd_sdk.contract.models import ChosenRepository, RepositoryRequirements
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

ENTRY = {
    "repository_id": DURHAM,
    "institution_name": "Durham University",
    "institution_ror": "https://ror.org/01v29qb04",
    "charges_deposit_fee": False,
}


def profile(entries: Any) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["institution_repositories"] = entries
    return Profile.from_mapping(data, source="test", digest="0" * 64)


def sources(tmp_path: Path) -> Sources:
    return Sources.from_config(registry(tmp_path / "registries", datacite=DATACITE_RECORDS))


# --- the profile key ------------------------------------------------------------------------


def test_the_profile_names_its_repositories_by_a_registrys_identifier() -> None:
    (entry,) = profile([ENTRY]).institution_repositories
    assert entry.repository_id == DURHAM
    assert entry.profile_ref == "profile:test-permissive@v9"
    assert entry.charges_deposit_fee is False
    assert profile(None).institution_repositories == ()


@pytest.mark.parametrize(
    ("entries", "says"),
    [
        ([{"repository_id": "Durham repository"}], "neither a re3data identifier"),
        ([{"repository_id": "r3d1234"}], "neither a re3data identifier"),
        ([ENTRY, ENTRY], "twice"),
        ([{**ENTRY, "description": "described by hand"}], "nothing reads"),
        ([{**ENTRY, "profile_ref": "profile:other@v1"}], "nothing reads"),
        ({"repository_id": DURHAM}, "must list"),
    ],
)
def test_a_malformed_entry_stops_the_profile_loading(entries: Any, says: str) -> None:
    with pytest.raises(PolicyError, match=says):
        profile(entries)


def test_the_source_check_resolves_what_the_profile_vouches_for_against_the_profile() -> None:
    held = profile([ENTRY])
    (document,) = institution_repositories.documents(held.institution_repositories)
    evidence = {
        "source_id": f"institution:{DURHAM}",
        "snapshot_ref": held.ref,
        "canonicalisation": DOCUMENT_CANONICALISATION,
        "content_hash": content_hash(document, DOCUMENT_CANONICALISATION),
    }
    with_profile = Sources().with_resolvers(institution_repositories.resolvers(held))
    assert check({"evidence": [evidence]}, with_profile).verified == 1
    forged = {**evidence, "content_hash": "f" * 64}
    assert not check({"evidence": [forged]}, with_profile).passed
    # Without the profile's resolver, the same evidence is unresolved, not verified.
    assert check({"evidence": [evidence]}, Sources()).unresolved
    assert institution_repositories.resolvers(profile(None)) == {}


# --- the DataCite snapshot beside the re3data export ----------------------------------------


def test_a_search_finds_a_repository_only_datacite_registers_and_never_one_twice(
    tmp_path: Path,
) -> None:
    held = sources(tmp_path)
    (found,) = held.find_repositories("Durham")
    assert (found.repository_id, found.registry, found.re3data_id) == (DURHAM, "datacite", None)
    assert [m.repository_id for m in held.find_repositories(DURHAM)] == [DURHAM]
    # DataCite's record at ORDA's address is ORDA, which re3data describes.
    assert [m.repository_id for m in held.find_repositories("ORDA")] == [ORDA]
    assert [m.repository_id for m in held.repositories([DURHAM, ORDA, "bl.shef"])] == [DURHAM, ORDA]


def test_a_datacite_repository_declares_the_datacite_standard_whose_dois_it_registers(
    tmp_path: Path,
) -> None:
    entry = sources(tmp_path).repository(DURHAM)
    assert entry is not None
    assert (entry.repository_id, entry.re3data_id) == (DURHAM, None)
    assert entry.snapshot_ref == DATACITE_SNAPSHOT
    assert entry.metadata_standards == ("DataCite Metadata Schema",)
    assert entry.content_hash == content_hash(DATACITE_RECORDS[0], DOCUMENT_CANONICALISATION)
    assert sources(tmp_path).repository("bl.unknown") is None


# --- a choice by either registry's identifier -----------------------------------------------


def test_a_repository_only_datacite_registers_can_be_chosen_and_is_recorded_by_its_id(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    requirements = load_requirements(
        write(tmp_path / "repositories", ("standards", standard()), ("overrides", override()))
    )
    store.choose_repository(
        project_id,
        DURHAM,
        registry=sources(tmp_path),
        requirements=requirements,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    (event,) = [e for e in store.events(project_id) if e["event"] == REPOSITORY_CHOSEN]
    assert (event["repository_id"], event["re3data_id"]) == (DURHAM, None)
    assert event["snapshot_ref"] == DATACITE_SNAPSHOT
    # It registers DataCite DOIs, so DataCite's set is no fallback; only the lack of an
    # override is warned of.
    assert len(event["warnings"]) == 1 and "no override" in event["warnings"][0]
    merged = RepositoryRequirements.model_validate(store.requirements(project_id))
    assert (merged.repository_id, merged.re3data_id) == (DURHAM, None)
    chosen = agent_slots.chosen(store.summary(project_id)["repository"])
    assert chosen == {
        "chosen_repository_name": "Durham University Repositories",
        "chosen_repository_id": DURHAM,
    }
    ChosenRepository.model_validate(chosen)


def test_an_override_may_name_a_repository_re3data_does_not_list(tmp_path: Path) -> None:
    durham = override(requirement_set_id="durham", re3data_id=None, repository_id=DURHAM)
    requirements = load_requirements(
        write(tmp_path / "repositories", ("standards", standard()), ("overrides", durham))
    )
    resolved = requirements.resolve(DURHAM, "Durham University Repositories")
    assert [s.ref for s in resolved.sets] == ["datacite-4@v1", "durham@v2"]
    assert resolved.warnings == ()
    both = override(requirement_set_id="both", repository_id=DURHAM)
    with pytest.raises(RequirementsError, match="names its repository once"):
        load_requirements(write(tmp_path / "both", ("standards", standard()), ("overrides", both)))


def test_a_choice_recorded_before_repositories_had_their_own_identifier_still_reads() -> None:
    old = {"chosen_repository_name": "ORDA", "chosen_re3data_id": ORDA}
    assert ChosenRepository.model_validate(old).chosen_repository_id == ORDA
    kept = {
        "re3data_id": ORDA,
        "repository_name": "ORDA",
        "conforms_to": "http://datacite.org/schema/kernel-4",
        "requirement_sets": [],
    }
    assert RepositoryRequirements.model_validate(kept).repository_id == ORDA


def test_a_repository_no_pinned_registry_holds_is_found_before_start_up(tmp_path: Path) -> None:
    held = profile([ENTRY, {"repository_id": "bl.nowhere"}, {"repository_id": ORDA}])
    named = institution_repositories.ids(held)
    assert sources(tmp_path).unheld(named) == ["bl.nowhere"]
    # Without a pinned registry nothing can be checked, and nothing is taken as missing.
    assert Sources().unheld(named) == []
