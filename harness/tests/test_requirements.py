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
    """The person depositing by hand is told where the repository is, what its sets leave open and
    where their values came from; only an override says where to deposit, since a standard's url
    describes the standard."""
    root = write(
        tmp_path / "repositories",
        (
            "standards",
            standard(
                url="https://datacite.org/",
                unconfirmed=["A", "B"],
                guidance=["https://a.example/", "https://b.example/"],
            ),
        ),
        (
            "overrides",
            override(
                url="https://orda.example/",
                unconfirmed=["B", "C"],
                guidance=["https://b.example/", "https://c.example/"],
            ),
        ),
    )
    requirements = load_requirements(root)
    ours = requirements.resolve(ORDA, "ORDA", ["Dublin Core"]).requirements()
    assert ours["repository_url"] == "https://orda.example/"
    assert ours["unconfirmed"] == ["A", "B", "C"]
    assert ours["guidance"] == ["https://a.example/", "https://b.example/", "https://c.example/"]
    other = requirements.resolve(ELSEWHERE, "Elsewhere", ["DataCite Metadata Schema"])
    assert "repository_url" not in other.requirements()
    assert other.requirements()["unconfirmed"] == ["A", "B"]
    assert other.requirements()["guidance"] == ["https://a.example/", "https://b.example/"]


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
    with pytest.raises(RequirementsError, match="neither a re3data identifier"):
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
            "names its repository once",
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
                                "term": "schema:name",
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
                                "term": "schema:description",
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
                            {"property": "titles", "term": "schema:name", "obligation": "required"},
                            {
                                "property": "creators",
                                "term": "schema:name",
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


# --- Terms (docs/specs/metadata-standards.md, invariants 7 and 8; #1357) -------------------------

LINEAGE = {
    "property": "descriptions",
    "qualifier": {"descriptionType": "Methods"},
    "term": "dcterms:provenance",
    "obligation": "required",
    "form_label": "Lineage",
}


def test_a_field_may_name_a_term_of_another_vocabulary(tmp_path: Path) -> None:
    folder = write(tmp_path, ("standards", standard()), ("overrides", override(fields=[LINEAGE])))
    merged = load_requirements(folder).resolve(ORDA, "ORDA", []).requirements()
    assert "dcterms:provenance" in [f["term"] for f in merged["fields"]]
    RepositoryRequirements.model_validate(merged)


def test_an_override_names_its_standards_field_by_curie_or_iri_alike(tmp_path: Path) -> None:
    """A field is identified by its term's IRI, so an override raising the abstract by its IRI
    raises the standard's field rather than adding a second one under the same term."""
    abstract = {
        "property": "descriptions",
        "qualifier": {"descriptionType": "Abstract"},
        "term": "http://schema.org/description",
        "obligation": "required",
    }
    folder = write(tmp_path, ("standards", standard()), ("overrides", override(fields=[abstract])))
    merged = load_requirements(folder).resolve(ORDA, "ORDA", []).requirements()
    descriptions = [f for f in merged["fields"] if f["property"] == "descriptions"]
    assert [f["obligation"] for f in descriptions] == ["required"]


def test_two_fields_under_one_iri_are_refused_however_it_is_written(tmp_path: Path) -> None:
    fields = [
        {"property": "titles", "term": "schema:name", "obligation": "required"},
        {"property": "creators", "term": "http://schema.org/name", "obligation": "required"},
    ]
    folder = write(tmp_path, ("standards", standard(fields=fields)))
    with pytest.raises(RequirementsError, match="maps both"):
        load_requirements(folder)


@pytest.mark.parametrize(
    "term", ["foaf:name", "dd:lineage", "name", "https://example.org/terms/lineage"]
)
def test_a_term_outside_the_registered_vocabularies_is_refused(tmp_path: Path, term: str) -> None:
    fields = [{"property": "titles", "term": term, "obligation": "required"}]
    folder = write(tmp_path, ("standards", standard(fields=fields)))
    with pytest.raises(RequirementsError, match="not a RequirementSet"):
        load_requirements(folder)


def test_a_set_written_before_terms_were_iris_reads_as_schema_org(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fields = [
        {"property": "titles", "schema_org": "name", "obligation": "required"},
        {"property": "subjects", "schema_org": "keywords", "obligation": "required"},
    ]
    folder = write(tmp_path, ("standards", standard(fields=fields)))
    with caplog.at_level("WARNING", logger="dd_harness.requirements"):
        resolved = load_requirements(folder).resolve(ELSEWHERE, "Elsewhere", [])
    assert [f["term"] for f in resolved.requirements()["fields"]] == [
        "schema:name",
        "schema:keywords",
    ]
    assert any("schema_org" in r.getMessage() for r in caplog.records)


def test_a_field_may_leave_its_term_to_its_standards_definition(tmp_path: Path) -> None:
    """docs/specs/metadata-standards.md: the term a field is read under is its standard's."""
    fields = [
        {"property": "titles", "obligation": "required"},
        {
            "property": "descriptions",
            "qualifier": {"descriptionType": "Methods"},
            "obligation": "recommended",
        },
    ]
    root = write(tmp_path / "repositories", ("standards", standard(fields=fields)))
    merged = load_requirements(root).resolve(ELSEWHERE, "Elsewhere").requirements()
    assert [f["term"] for f in merged["fields"]] == [
        "http://schema.org/name",
        "http://purl.org/dc/terms/provenance",
    ]


def test_a_field_that_names_another_term_than_its_standards_is_refused(tmp_path: Path) -> None:
    fields = [{"property": "titles", "term": "schema:headline", "obligation": "required"}]
    root = write(tmp_path / "repositories", ("standards", standard(fields=fields)))
    with pytest.raises(RequirementsError, match=r"datacite-4@v\d+ gives it http://schema.org/name"):
        load_requirements(root)


def test_a_set_whose_standard_no_definition_covers_stops_start_up(tmp_path: Path) -> None:
    """docs/specs/metadata-standards.md, invariant 11."""
    other = standard(
        requirement_set_id="ddi",
        conforms_to="https://ddialliance.org/Specification/DDI-Codebook/2.5/",
        re3data_names=["DDI"],
        fields=[{"property": "title", "term": "schema:name", "obligation": "required"}],
    )
    root = write(tmp_path / "repositories", ("standards", standard()), ("standards", other))
    with pytest.raises(RequirementsError, match="no registered standard's definition covers"):
        load_requirements(root)
