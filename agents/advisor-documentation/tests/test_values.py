"""The Documentation Editor is given a field's summary values, never more (values.py, #571):
the writer sees them as `values`, and the data dictionary takes missing-value codes as inferred."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.dictionary import Source
from dd_agent_advisor_documentation.values import field_facts, missing_codes
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.inventory import (
    CategoryCount,
    DisclosureCheck,
    FieldSummary,
    MissingCodeCount,
)
from dd_sdk.contract.models import Document, DraftRequest, OutcomeStatus, TableField

SAMPLES = Path(__file__).with_name("data")
CHECK = DisclosureCheck(
    check_tool="acro",
    check_tool_version="1.1.0",
    check_threshold=10,
    check_rounding_base=5,
    check_suppressed=1,
)
SUMMARY = FieldSummary(
    summary_rows_read=200,
    summary_range_low="27",
    summary_range_high="62",
    summary_mean=44.752941176,
    summary_missing_codes=[MissingCodeCount(missing_code="-99", missing_code_count=30)],
)


def test_a_field_without_summaries_is_as_before() -> None:
    field = TableField(name="ph", field_type="number")
    assert field_facts(field) == {"name": "ph", "type": "number"}
    assert missing_codes(field) == ""


def test_a_writer_is_told_a_range_is_not_the_extremes() -> None:
    field = TableField(
        name="age", field_type="integer", field_summary=SUMMARY, field_disclosure_check=CHECK
    )
    values = field_facts(field)["values"]
    assert values["range"]["low"] == "27" and values["range"]["high"] == "62"
    assert values["range"][
        "note"
    ]  # what a range is, so that a writer does not call it the extremes
    assert values["mean"] == 44.7529
    assert values["missing_value_codes"] == {"-99": 30}
    assert values["rows_read"] == 200
    assert values["left_out"]
    assert missing_codes(field) == '["-99"]'


def test_categories_are_given_with_their_counts() -> None:
    summary = FieldSummary(
        summary_categories=[CategoryCount(category_value="eczema", category_count=70)]
    )
    field = TableField(name="diagnosis", field_summary=summary, field_disclosure_check=CHECK)
    assert field_facts(field)["values"]["categories"] == {"eczema": 70}


def test_the_dictionary_infers_missing_value_codes(runs_dir: Path) -> None:
    asked = DraftRequest.model_validate_json(
        (SAMPLES / "soil-survey.data-dictionary.draft.json").read_text(encoding="utf-8")
    )
    assert asked.inventory is not None
    files = list(asked.inventory.inventory_files)
    table = next(i for i, f in enumerate(files) if f.file_fields)
    first = (
        files[table]
        .file_fields[0]
        .model_copy(update={"field_summary": SUMMARY, "field_disclosure_check": CHECK})
    )
    files[table] = files[table].model_copy(
        update={"file_fields": [first, *files[table].file_fields[1:]]}
    )
    asked = asked.model_copy(
        update={"inventory": asked.inventory.model_copy(update={"inventory_files": files})}
    )
    conductor = make_conductor(runs_dir, DocumentationEditor())
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    rows = list(csv.DictReader(io.StringIO(env.payload_as(Document).document_text)))
    row = next(r for r in rows if (r["file"], r["field"]) == (files[table].file_path, first.name))
    assert (row["missing_values"], row["missing_values_source"]) == ('["-99"]', Source.INFERRED)
    others = [r for r in rows if r is not row]
    assert all(r["missing_values_source"] == Source.UNKNOWN for r in others)
