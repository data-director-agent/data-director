"""Repository requirements: a standard's set, an optional override, and what a choice resolves to
(docs/specs/deposit.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ELSEWHERE, ORDA, override, standard, write

from dd_harness.requirements import DATACITE, RequirementsError, load_requirements
from dd_sdk.contract.models import RepositoryRequirements

ZENODO_SANDBOX = {
    "transport": "zenodo",
    "format": "zenodo-deposit",
    "base_url": "https://sandbox.zenodo.org/api",
    "sandbox": True,
}


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


def test_the_merged_set_says_where_to_deposit_and_what_is_unconfirmed(tmp_path: Path) -> None:
    """The person depositing by hand is told where the repository is and what its sets leave
    open; only an override says where to deposit, since a standard's url describes the standard."""
    root = write(
        tmp_path / "repositories",
        ("standards", standard(url="https://datacite.org/", unconfirmed=["A", "B"])),
        ("overrides", override(url="https://orda.example/", unconfirmed=["B", "C"])),
    )
    requirements = load_requirements(root)
    ours = requirements.resolve(ORDA, "ORDA", ["Dublin Core"]).requirements()
    assert ours["repository_url"] == "https://orda.example/"
    assert ours["unconfirmed"] == ["A", "B", "C"]
    other = requirements.resolve(ELSEWHERE, "Elsewhere", ["DataCite Metadata Schema"])
    assert "repository_url" not in other.requirements()
    assert other.requirements()["unconfirmed"] == ["A", "B"]


@pytest.mark.parametrize(
    ("re3data_id", "name", "declared"),
    [(ORDA, "ORDA", ["Dublin Core"]), (ELSEWHERE, "Elsewhere", ["Dublin Core"])],
)
def test_the_merged_set_is_the_core_class_a_drafter_is_given(
    sets: Path, re3data_id: str, name: str, declared: list[str]
) -> None:
    """A drafter reads the merged set as `DraftRequest.requirements` (#200), so it must parse as
    the core `RepositoryRequirements`, which forbids any key it does not name."""
    merged = load_requirements(sets).resolve(re3data_id, name, declared).requirements()
    parsed = RepositoryRequirements.model_validate(merged)
    assert parsed.model_dump(mode="json", exclude_none=True, exclude_defaults=True).items() <= (
        merged.items()
    )


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
                (
                    "overrides",
                    override(
                        fields=[
                            {
                                "property": "descriptions",
                                "qualifier": {"descriptionType": "Methods"},
                                "schema_org": "description",
                                "obligation": "required",
                                "form_label": "Lineage",
                            }
                        ]
                    ),
                ),
            ),
            "maps both descriptions .*Abstract.* and descriptions .*Methods.* to "
            "schema:description",
        ),
        (
            (
                (
                    "standards",
                    standard(
                        fields=[
                            {"property": "titles", "schema_org": "name", "obligation": "required"},
                            {
                                "property": "creators",
                                "schema_org": "name",
                                "obligation": "required",
                            },
                        ]
                    ),
                ),
            ),
            "maps both titles and creators to schema:name",
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
        (
            (("standards", standard(deposit=ZENODO_SANDBOX)),),
            "standard's set may not give deposit",
        ),
        (
            (
                ("standards", standard()),
                ("overrides", override(deposit={**ZENODO_SANDBOX, "format": "bagit"})),
            ),
            "not a pair docs/specs/deposit.md allows",
        ),
        (
            (
                ("standards", standard()),
                ("overrides", override(deposit={**ZENODO_SANDBOX, "base_url": "http://x"})),
            ),
            "not a RequirementSet",
        ),
        (
            (
                ("standards", standard()),
                ("overrides", override(deposit={**ZENODO_SANDBOX, "token": "secret"})),
            ),
            "not a RequirementSet",
        ),
    ],
)
def test_malformed_or_contradictory_sets_stop_start_up(
    tmp_path: Path, sets_given: tuple[tuple[str, dict[str, Any]], ...], refusal: str
) -> None:
    root = write(tmp_path / "repositories", *sets_given)
    with pytest.raises(RequirementsError, match=refusal):
        load_requirements(root)


def test_an_override_may_name_the_api_a_draft_is_deposited_through(tmp_path: Path) -> None:
    """Only an override names a connector, and it holds no credential; a repository without one
    is deposited to by hand (docs/specs/deposit.md, invariants 11 and 18)."""
    root = write(
        tmp_path / "repositories",
        ("standards", standard()),
        ("overrides", override(deposit=ZENODO_SANDBOX)),
    )
    requirements = load_requirements(root)
    connector = requirements.connector(ORDA)
    assert connector is not None
    assert (connector.transport, connector.format) == ("zenodo", "zenodo-deposit")
    assert connector.base_url == "https://sandbox.zenodo.org/api"
    assert connector.sandbox is True
    assert requirements.connector(ELSEWHERE) is None
    # The merged set a drafter is given says nothing of how the package travels.
    assert "deposit" not in requirements.resolve(ORDA, "ORDA").requirements()


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RequirementsError, match="not found"):
        load_requirements(tmp_path / "nowhere")


def test_the_suggested_repositories_are_the_overrides_then_the_listed_ones(sets: Path) -> None:
    assert load_requirements(sets).suggested == (ORDA,)
    (sets / "suggested.yaml").write_text(f"re3data_ids: [{ELSEWHERE}, {ORDA}]\n", encoding="utf-8")
    assert load_requirements(sets).suggested == (ORDA, ELSEWHERE)


@pytest.mark.parametrize("text", ["re3data_ids: [orda]\n", "re3data_ids: r3d100012124\n", "[\n"])
def test_a_malformed_suggested_list_stops_start_up(sets: Path, text: str) -> None:
    (sets / "suggested.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(RequirementsError):
        load_requirements(sets)
