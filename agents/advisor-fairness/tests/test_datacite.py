"""Reading a DataCite record in DataCite's JSON form as the fields the assessor checks."""

from __future__ import annotations

import json

import pytest

from dd_agent_advisor_fairness.classes import PublishedRecord
from dd_agent_advisor_fairness.datacite import NotDataCiteError, fields

ORCID = "https://orcid.org/0000-0002-1825-0097"
RECORD = {
    "doi": "10.15131/shef.data.12345",
    "titles": [{"title": "Peat depth survey, 2025"}],
    "descriptions": [{"description": "Probe depths at 400 points.", "descriptionType": "Abstract"}],
    "rightsList": [{"rights": "Creative Commons Attribution 4.0", "rightsIdentifier": "CC-BY-4.0"}],
    "subjects": [{"subject": "peatland"}, {"subject": None}],
    "creators": [
        {
            "name": "Byron, Ada",
            "nameIdentifiers": [{"nameIdentifier": ORCID, "nameIdentifierScheme": "ORCID"}],
        },
        {"name": "Babbage, Charles"},
    ],
    "formats": ["text/csv", None],
    "relatedIdentifiers": [{"relatedIdentifier": "10.1000/article", "relationType": "IsCitedBy"}],
}


def test_each_given_value_is_read_into_its_field() -> None:
    read = PublishedRecord.model_validate(fields(json.dumps(RECORD)))
    assert read.identifier == RECORD["doi"]
    assert read.title and read.description
    assert read.licence == "CC-BY-4.0"
    assert read.keywords == ["peatland"]
    assert len(read.creators) == 2
    assert read.creator_identifiers == [ORCID]
    assert read.formats == ["text/csv"]
    assert read.related_identifiers == ["10.1000/article"]


def test_values_left_null_for_the_researcher_read_as_absent() -> None:
    draft = dict.fromkeys(RECORD)
    read = PublishedRecord.model_validate(fields(json.dumps(draft)))
    assert read == PublishedRecord()


def test_a_rights_statement_without_an_identifier_is_the_licence() -> None:
    read = fields(json.dumps({"rightsList": [{"rights": "All rights reserved"}]}))
    assert read["licence"] == "All rights reserved"


def test_a_rest_api_response_is_read_from_its_attributes() -> None:
    read = fields(json.dumps({"id": "x", "type": "dois", "attributes": RECORD}))
    assert read["identifier"] == RECORD["doi"]


@pytest.mark.parametrize("text", ["not json", "[1, 2]", '"a string"'])
def test_text_that_is_not_a_json_object_is_refused(text: str) -> None:
    with pytest.raises(NotDataCiteError):
        fields(text)
