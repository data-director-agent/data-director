"""dd-metadata-records: codecs, standards' definitions and the pivot
(docs/specs/metadata-standards.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_metadata_records import (
    JSON,
    MAX_RECORD_BYTES,
    CodecError,
    DefinitionError,
    Pivot,
    RecordError,
    Standards,
    discover,
    load,
)
from dd_metadata_records.standards import DATACITE_4

DATACITE = "http://datacite.org/schema/kernel-4"
SCHEMA = "http://schema.org/"
DCTERMS = "http://purl.org/dc/terms/"
RECORD = {
    "titles": [{"title": "Soil cores"}, {"title": "Cores", "titleType": "AlternativeTitle"}],
    "creators": [
        {
            "name": "Carberry, Josiah",
            "nameIdentifiers": [
                {"nameIdentifier": "0000-0002-1825-0097", "nameIdentifierScheme": "ORCID"}
            ],
            "affiliation": [{"name": "University of Sheffield"}],
        },
        {"name": None, "familyName": "Lovelace", "givenName": "Ada"},
    ],
    "subjects": [
        {"subject": "soil science"},
        {"subject": "Soil sciences", "subjectScheme": "ANZSRC Fields of Research"},
    ],
    "descriptions": [
        {"description": "Cores taken in 2026.", "descriptionType": "Abstract"},
        {"description": "Augered.", "descriptionType": "Methods"},
    ],
    "dates": [{"date": "2026-04-01", "dateType": "Created"}],
    "types": {"resourceTypeGeneral": "Dataset"},
    "publicationYear": 2026,
    "version": None,
    "somethingElse": "kept",
}


def datacite() -> Standards:
    return Standards([DATACITE_4], [JSON])


def test_the_json_codec_writes_the_same_text_for_the_same_tree() -> None:
    tree = {"b": [1, {"c": None}], "a": "é"}
    text = JSON.emit(tree)
    assert text == json.dumps(tree, ensure_ascii=False, indent=2) + "\n"
    assert JSON.emit(JSON.parse(text)) == text


def test_a_codec_refuses_text_over_the_limit_and_text_not_in_it() -> None:
    with pytest.raises(CodecError, match="over"):
        JSON.parse(" " * (MAX_RECORD_BYTES + 1))
    with pytest.raises(CodecError, match="not JSON"):
        JSON.parse("Title: soil")


def test_a_record_is_read_only_in_a_pair_a_definition_covers() -> None:
    standards = datacite()
    assert standards.covering(DATACITE, "application/json") is not None
    assert standards.covering(DATACITE, "application/xml") is None
    assert standards.covering("http://purl.org/dc/elements/1.1/", "application/json") is None
    assert standards.covering(None, "application/json") is None


def test_a_record_inside_an_api_envelope_is_read_from_inside_it() -> None:
    standard = datacite().covering(DATACITE, "application/json")
    assert standard is not None
    wrapped = json.dumps({"data": {"attributes": RECORD}})
    assert standard.read(wrapped, "application/json").values("titles") == [
        "Soil cores",
        "Cores",
    ]
    with pytest.raises(RecordError, match="not a JSON object"):
        standard.read("[]", "application/json")


def test_values_follow_a_requirement_fields_property_and_qualifier() -> None:
    standard = datacite().covering(DATACITE, "application/json")
    assert standard is not None
    record = standard.read(json.dumps(RECORD), "application/json")
    assert record.values("descriptions", {"descriptionType": "Abstract"}) == [
        "Cores taken in 2026."
    ]
    assert record.values("types.resourceTypeGeneral") == ["Dataset"]
    assert record.values("publicationYear") == ["2026"]
    # A gap is no value (invariant 6).
    assert record.values("version") == []


def test_the_pivot_holds_each_entry_under_its_term_with_its_parts() -> None:
    standard = datacite().covering(DATACITE, "application/json")
    assert standard is not None
    pivot = standard.read(json.dumps(RECORD), "application/json").pivot()
    assert isinstance(pivot, Pivot)
    assert pivot.values_of(SCHEMA + "keywords") == ["soil science"]
    assert pivot.values_of(SCHEMA + "about") == ["Soil sciences"]
    assert pivot.values_of(SCHEMA + "description") == ["Cores taken in 2026."]
    assert pivot.values_of(DCTERMS + "provenance") == ["Augered."]
    assert pivot.values_of(SCHEMA + "dateCreated") == ["2026-04-01"]
    first, second = pivot[SCHEMA + "creator"]
    assert first.part(SCHEMA + "affiliation") == ["University of Sheffield"]
    (orcid,) = first.parts[SCHEMA + "identifier"]
    assert orcid.part(SCHEMA + "propertyID") == ["ORCID"]
    assert second.value is None and second.part(SCHEMA + "familyName") == ["Lovelace"]
    assert {node.path for nodes in pivot.values() for node in nodes} >= {"titles", "creators"}
    # What no term holds is named, never dropped silently.
    assert pivot.unmapped == ("somethingElse",)


def test_a_requirement_fields_term_comes_from_the_definition() -> None:
    assert DATACITE_4.term("titles") == SCHEMA + "name"
    assert DATACITE_4.term("descriptions", {"descriptionType": "Methods"}) == DCTERMS + "provenance"
    assert DATACITE_4.term("subjects", {"subjectScheme": "ANZSRC"}) == SCHEMA + "about"
    assert DATACITE_4.term("noSuchProperty") is None


def test_the_definition_names_itself_for_the_project_log() -> None:
    described = DATACITE_4.describe()
    assert described["ref"] == "datacite-4@v1"
    assert len(described["sha256"]) == 64
    assert described["codecs"] == {JSON.media_type: JSON.codec_id}


def test_the_installed_standards_are_discovered() -> None:
    assert discover().by_uri(DATACITE) is not None


def test_a_definition_that_names_an_unregistered_codec_is_refused() -> None:
    with pytest.raises(DefinitionError, match="no such codec"):
        Standards([DATACITE_4], [])


def test_a_definition_with_an_invented_vocabulary_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        "standard_id: bad\nversion: 1\ntitle: Bad\nurl: x\nconforms_to: [x]\n"
        "serialisations: [{media_type: application/json, name: JSON, codec: json-indent-2}]\n"
        "properties: {title: 'my:title'}\n",
        encoding="utf-8",
    )
    with pytest.raises(DefinitionError, match="not a term"):
        load(path)
