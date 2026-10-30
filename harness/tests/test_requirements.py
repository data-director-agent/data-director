"""Repository requirements: a standard's set, an optional override, and what a choice resolves to
(ADR-0038)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ELSEWHERE, ORDA, override, standard, write

from dd_harness.requirements import DATACITE, RequirementsError, load_requirements


@pytest.fixture
def sets(tmp_path: Path) -> Path:
    return write(tmp_path / "repositories", ("standards", standard()), ("overrides", override()))


def test_an_override_is_merged_on_its_standard(sets: Path) -> None:
    # re3data lists only Dublin Core for ORDA: the override names the standard, not the registry.
    resolved = load_requirements(sets).resolve(ORDA, "ORDA", ["Dublin Core"])
    assert [s.ref for s in resolved.sets] == ["datacite-4@v1", "orda@v2"]
    assert resolved.warnings == ()
    merged = resolved.requirements()
    assert merged["conforms_to"] == DATACITE
    assert [(f["property"], f["obligation"], f.get("form_label")) for f in merged["fields"]] == [
        ("titles", "required", "Title"),
        ("descriptions", "required", "Description"),  # raised from recommended
        ("subjects", "required", "Keywords"),  # added
    ]
    assert merged["required_documents"] == ["metadata_record"]
    assert merged["recommended_documents"] == ["readme"]
    assert merged["licences"] == ["CC-BY-4.0"]
    assert [s["ref"] for s in merged["requirement_sets"]] == ["datacite-4@v1", "orda@v2"]
    assert all(len(s["sha256"]) == 64 for s in merged["requirement_sets"])


def test_without_an_override_the_declared_standard_applies_and_the_researcher_is_warned(
    sets: Path,
) -> None:
    resolved = load_requirements(sets).resolve(ELSEWHERE, "Elsewhere", ["DataCite Metadata Schema"])
    assert [s.ref for s in resolved.sets] == ["datacite-4@v1"]
    (warning,) = resolved.warnings
    assert "no override for Elsewhere" in warning
    merged = resolved.requirements()
    assert [f["obligation"] for f in merged["fields"]] == ["required", "recommended"]
    assert "licences" not in merged and "media_types" not in merged


def test_a_repository_that_declares_no_known_standard_is_checked_against_datacite(
    sets: Path,
) -> None:
    resolved = load_requirements(sets).resolve(ELSEWHERE, "Elsewhere", ["Dublin Core"])
    assert resolved.standard.requirement_set.conforms_to == DATACITE
    does_not_list, no_override = resolved.warnings
    assert "does not list DataCite" in does_not_list and "Dublin Core" in does_not_list
    assert "no override" in no_override


def test_a_choice_needs_a_re3data_identifier_and_a_name(sets: Path) -> None:
    requirements = load_requirements(sets)
    with pytest.raises(RequirementsError, match="not a re3data identifier"):
        requirements.resolve("orda", "ORDA")
    with pytest.raises(RequirementsError, match="needs its name"):
        requirements.resolve(ORDA, " ")


@pytest.mark.parametrize(
    ("sets_given", "refusal"),
    [
        ((("standards", standard(repository_id="x")),), "not a RequirementSet"),
        ((("standards", standard(licences=["MIT"])),), "standard's set may not give licences"),
        ((("standards", standard(re3data_names=[])),), "names its standard in re3data_names"),
        (
            (("standards", standard()), ("overrides", override(re3data_id=None))),
            "names its repository in re3data_id",
        ),
        (
            (("standards", standard()), ("overrides", override(re3data_names=["x"]))),
            "override may not give re3data_names",
        ),
        (
            (
                ("standards", standard()),
                (
                    "overrides",
                    override(
                        fields=[
                            {
                                "property": "titles",
                                "schema_org": "name",
                                "obligation": "recommended",
                            }
                        ]
                    ),
                ),
            ),
            "lowers titles",
        ),
        (
            (
                ("standards", standard()),
                ("overrides", override(conforms_to="https://ddialliance.org")),
            ),
            "no standard's set",
        ),
        (
            (
                ("standards", standard()),
                ("standards", standard(requirement_set_id="other", re3data_names=["Other"])),
            ),
            "two requirement sets give conforms_to",
        ),
        (
            (("standards", standard(conforms_to="https://ddialliance.org")),),
            "no standard's set conforms to",
        ),
    ],
)
def test_malformed_or_contradictory_sets_stop_start_up(
    tmp_path: Path, sets_given: tuple[tuple[str, dict[str, Any]], ...], refusal: str
) -> None:
    root = write(tmp_path / "repositories", *sets_given)
    with pytest.raises(RequirementsError, match=refusal):
        load_requirements(root)


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RequirementsError, match="not found"):
        load_requirements(tmp_path / "nowhere")
