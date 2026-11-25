"""A record converted from one standard to another through the pivot, reporting what it loses
(docs/specs/metadata-standards.md, invariant 9; #1363)."""

from __future__ import annotations

import json
from typing import Any

from dd_metadata_records import JSON, XML, Reduced, Standards, convert
from dd_metadata_records.standards import DATACITE_4, DUBLIN_CORE_OAI

DATACITE = "http://datacite.org/schema/kernel-4"
OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
RECORD: dict[str, Any] = {
    "titles": [{"title": "Soil cores"}, {"title": "Cores", "titleType": "AlternativeTitle"}],
    "creators": [
        {
            "name": "Carberry, Josiah",
            "nameType": "Personal",
            "nameIdentifiers": [
                {"nameIdentifier": "0000-0002-1825-0097", "nameIdentifierScheme": "ORCID"}
            ],
        }
    ],
    "descriptions": [
        {"description": "Cores taken in 2026.", "descriptionType": "Abstract"},
        {"description": "Augered to 30 cm.", "descriptionType": "Methods"},
    ],
    "dates": [{"date": "2026-04", "dateType": "Collected"}],
    "types": {"resourceTypeGeneral": "Dataset"},
    "rightsList": [{"rights": "https://creativecommons.org/licenses/by/4.0/"}],
    "fundingReferences": [{"funderName": "NERC"}],
    "publicationYear": 2026,
}


def standards() -> Standards:
    return Standards([DATACITE_4, DUBLIN_CORE_OAI], [JSON, XML])


def read(conforms_to: str, text: str, media_type: str) -> Any:
    standard = standards().by_uri(conforms_to)
    assert standard is not None
    return standard.read(text, media_type)


def test_a_datacite_record_in_dublin_core_reports_what_it_loses_and_reduces() -> None:
    record = read(DATACITE, json.dumps(RECORD), "application/json")
    converted = convert(record, DUBLIN_CORE_OAI)
    assert converted.tree == {
        "title": ["Soil cores", "Cores"],
        "creator": ["Carberry, Josiah"],
        "description": ["Cores taken in 2026."],
        "type": ["Dataset"],
        "rights": ["https://creativecommons.org/licenses/by/4.0/"],
    }
    # Dublin Core has no element for the methods, the date of collection, the funder or the year.
    assert converted.unplaced == ("dates", "descriptions", "fundingReferences", "publicationYear")
    reduced = {r.path for r in converted.reduced}
    # The creator's name is kept without its ORCID iD or its type; the titles and the abstract
    # without the type that tells them apart.
    assert reduced == {"creators", "titles", "descriptions"}
    assert any("identifier" in r.reason for r in converted.reduced if r.path == "creators")


def test_dublin_core_and_back_keeps_what_both_standards_hold() -> None:
    record = read(DATACITE, json.dumps(RECORD), "application/json")
    dublin_core = standards().by_uri(OAI_DC)
    assert dublin_core is not None
    text = dublin_core.write(convert(record, DUBLIN_CORE_OAI).tree, "application/xml")
    back = convert(read(OAI_DC, text, "application/xml"), DATACITE_4)
    assert back.tree == {
        "titles": [{"title": "Soil cores"}, {"title": "Cores"}],
        "creators": [{"name": "Carberry, Josiah"}],
        "descriptions": [{"description": "Cores taken in 2026."}],
        "rightsList": [{"rights": "https://creativecommons.org/licenses/by/4.0/"}],
        "types": {"resourceTypeGeneral": "Dataset"},
    }
    # Every Dublin Core element it held has a DataCite property, so nothing more is lost.
    assert back.unplaced == () and back.reduced == ()


def test_a_second_value_where_the_target_holds_one_is_reduced() -> None:
    text = (
        f'<oai_dc:dc xmlns:oai_dc="{OAI_DC}" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:type>Dataset</dc:type><dc:type>Software</dc:type></oai_dc:dc>"
    )
    converted = convert(read(OAI_DC, text, "application/xml"), DATACITE_4)
    assert converted.tree == {"types": {"resourceTypeGeneral": "Dataset"}}
    assert converted.reduced == (
        Reduced("type", "DataCite holds one value where the source gives several"),
    )


def test_a_qualified_term_is_written_with_its_qualifier() -> None:
    """A Methods description is read as dcterms:provenance, and written back as one."""
    record = read(
        DATACITE, json.dumps({"descriptions": RECORD["descriptions"]}), "application/json"
    )
    converted = convert(record, DATACITE_4)
    assert converted.tree == {"descriptions": RECORD["descriptions"]}


def test_a_gap_is_not_copied() -> None:
    record = read(DATACITE, json.dumps({"titles": [{"title": None}]}), "application/json")
    assert convert(record, DUBLIN_CORE_OAI).tree == {}
