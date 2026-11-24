"""Dublin Core as OAI-DC, the XML codec that writes it, and what a DataCite record would lose in it
(docs/specs/metadata-standards.md; #1360)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from dd_metadata_records import (
    JSON,
    XML,
    CodecError,
    RecordError,
    Standards,
    unplaced,
)
from dd_metadata_records.standards import DATACITE_4, DUBLIN_CORE_OAI

XSD = Path(__file__).with_name("data") / "xsd"
OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC = "http://purl.org/dc/elements/1.1/"
SCHEMA = "http://schema.org/"


def dublin_core() -> Any:
    standard = Standards([DATACITE_4, DUBLIN_CORE_OAI], [JSON, XML]).by_uri(OAI_DC)
    assert standard is not None
    return standard


class _Local(etree.Resolver):  # type: ignore[misc]
    """Resolves each schema's import of the next to the copy kept in tests/data/xsd, unchanged."""

    def resolve(self, url: str, pubid: str | None, context: Any) -> Any:
        local = XSD / url.rsplit("/", 1)[-1]
        return self.resolve_filename(str(local), context) if local.is_file() else None


def oai_dc_schema() -> Any:
    parser = etree.XMLParser(no_network=True, load_dtd=False, resolve_entities=False)
    parser.resolvers.add(_Local())
    return etree.XMLSchema(etree.parse(str(XSD / "oai_dc.xsd"), parser))


def test_the_xml_codec_writes_the_same_text_for_the_same_tree() -> None:
    text = dublin_core().write({"title": ["Soil & cores"], "creator": None}, "application/xml")
    assert XML.emit(XML.parse(text)) == text
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<oai_dc:dc ')
    assert text.endswith("</oai_dc:dc>\n")


@pytest.mark.parametrize(
    "text",
    [
        '<!DOCTYPE dc [<!ENTITY x SYSTEM "file:///etc/passwd">]><dc>&x;</dc>',
        "<dc><title>unclosed</dc>",
        " " * 2_000_000,
    ],
)
def test_the_xml_codec_reads_only_the_record(text: str) -> None:
    """Invariant 13: no document type, no entity, nothing over the size limit."""
    with pytest.raises(CodecError):
        XML.parse(text)


def test_a_drafted_record_with_gaps_and_values_passes_the_oai_dc_schema() -> None:
    tree = {
        "title": None,
        "creator": ["Carberry, Josiah", None],
        "type": "Dataset",
        "subject": ["soil science"],
    }
    text = dublin_core().write(tree, "application/xml")
    schema = oai_dc_schema()
    document = etree.fromstring(text.encode("utf-8"))
    assert schema.validate(document), schema.error_log
    assert document.find(f"{{{DC}}}title").text == ":unav"


def test_a_gap_reads_back_as_no_value() -> None:
    """Invariant 6: `:unav` is a gap in OAI-DC, never a value."""
    text = dublin_core().write({"title": None, "creator": ["Carberry, Josiah"]}, "application/xml")
    record = dublin_core().read(text, "application/xml")
    assert record.values("title") == []
    assert record.values("creator") == ["Carberry, Josiah"]
    assert record.pivot().values_of(SCHEMA + "creator") == ["Carberry, Josiah"]


def test_an_element_the_definition_does_not_name_is_reported_not_dropped() -> None:
    text = (
        f'<oai_dc:dc xmlns:oai_dc="{OAI_DC}" xmlns:dc="{DC}" xmlns:x="https://example.org/x">'
        "<dc:title>Soil</dc:title><x:note>kept</x:note></oai_dc:dc>"
    )
    pivot = dublin_core().read(text, "application/xml").pivot()
    assert pivot.values_of(SCHEMA + "name") == ["Soil"]
    assert pivot.unmapped == ("note",)


def test_a_document_with_another_root_is_not_an_oai_dc_record() -> None:
    with pytest.raises(RecordError, match="root element"):
        dublin_core().read(f'<record xmlns="{DC}"/>', "application/xml")


def test_a_property_with_no_element_cannot_be_written() -> None:
    with pytest.raises(RecordError, match="no element for"):
        dublin_core().write({"titles": ["Soil"]}, "application/xml")


def test_dublin_core_reads_its_elements_under_datacites_terms_where_they_mean_the_same() -> None:
    for datacite, element in (
        ("titles", "title"),
        ("creators", "creator"),
        ("descriptions", "description"),
        ("types.resourceTypeGeneral", "type"),
        ("rightsList", "rights"),
    ):
        assert DATACITE_4.term(datacite) == DUBLIN_CORE_OAI.term(element), element


def test_a_datacite_record_names_what_dublin_core_could_not_hold() -> None:
    """#1360, done when: each property the conversion could not place is reported."""
    record = {
        "titles": [{"title": "Soil cores"}],
        "creators": [{"name": "Carberry, Josiah"}],
        "descriptions": [{"description": "Cores.", "descriptionType": "Abstract"}],
        "fundingReferences": [{"funderName": "NERC"}],
        "geoLocations": [{"geoLocationPlace": "Hope Valley"}],
        "sizes": ["2 files"],
        "somethingElse": "kept",
    }
    datacite = Standards([DATACITE_4], [JSON]).by_uri("http://datacite.org/schema/kernel-4")
    assert datacite is not None
    pivot = datacite.read(json.dumps(record), "application/json").pivot()
    assert unplaced(pivot, DUBLIN_CORE_OAI) == (
        "fundingReferences",
        "geoLocations",
        "sizes",
        "somethingElse",
    )
