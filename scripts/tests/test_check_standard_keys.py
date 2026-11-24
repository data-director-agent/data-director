"""The rule in scripts/check_standard_keys.py that no module outside a standard's definition names
one of its properties (docs/specs/metadata-standards.md, invariant 3)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_standard_keys as csk  # noqa: E402

DEFINITION = {
    "properties": {
        "titles": {"value": "title", "parts": {"titleType": "dcterms:type"}},
        "types.resourceTypeGeneral": "schema:additionalType",
        "dates": {"value": "date", "qualified": [{"when": {"dateType": "Created"}, "term": "x"}]},
    }
}


def test_only_camel_case_and_dotted_identifiers_are_distinctive() -> None:
    found = csk.identifiers(DEFINITION)
    assert {"titleType", "types.resourceTypeGeneral", "resourceTypeGeneral", "dateType"} <= found
    assert not {"titles", "title", "dates", "date", "types"} & found


def test_a_literal_is_reported_and_a_docstring_is_not() -> None:
    source = '"""Reads rightsList."""\n\nKEY = "rightsList"\nOTHER = "rights"\n'
    assert csk.named(source, {"rightsList"}) == [(3, "rightsList")]


def test_a_member_that_names_a_property_fails(tmp_path: Path) -> None:
    module = tmp_path / "harness" / "src" / "pkg" / "reader.py"
    module.parent.mkdir(parents=True)
    module.write_text('VALUE = record["geoLocations"]\n', encoding="utf-8")
    found = csk.problems([module], {"geoLocations"}, root=tmp_path)
    assert any(line.startswith("harness/src/pkg/reader.py:1:") for line in found)


def test_the_repository_passes() -> None:
    assert csk.problems(csk.sources(), csk.all_identifiers()) == []
