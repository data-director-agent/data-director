"""Name-level hints shared by advisor.files and the harness's deposit check
(dd_sdk.inventory_hints, docs/specs/personal-data.md)."""

from __future__ import annotations

from dd_sdk.contract.models import IdentificationMethod, InventoryFile, TableField
from dd_sdk.inventory_hints import RULES, HintKind, hints


def file(path: str, *fields: str, size: int = 10, digest: int = 0) -> InventoryFile:
    return InventoryFile(
        file_path=path,
        file_size=size,
        file_sha256=f"{digest or hash(path) & 0xFFFF:064x}",
        file_identified_by=IdentificationMethod.EXTENSION,
        file_fields=[TableField(name=f, field_type="string") for f in fields],
    )


def test_every_kind_has_a_rule_and_a_question() -> None:
    assert [rule.kind for rule in RULES] == list(HintKind)
    assert all(rule.question for rule in RULES)


def test_hints_come_file_by_file_with_what_called_for_them() -> None:
    found = hints(
        [
            file("fieldnotes/day1.txt"),
            file("calibration/sites.csv", "node", "lat"),
            file("data/readings.csv", "site", "value"),
            file("a.csv", digest=7),
            file("b/a.csv", digest=7),
            file("data/Thumbs.db", size=0),
        ]
    )
    assert [(h.path, h.kind, h.matched) for h in found] == [
        ("fieldnotes/day1.txt", HintKind.FREE_TEXT, "fieldnotes"),
        ("calibration/sites.csv", HintKind.COORDINATES, "lat"),
        ("a.csv", HintKind.DUPLICATE, None),
        ("b/a.csv", HintKind.DUPLICATE, None),
        ("data/Thumbs.db", HintKind.SYSTEM_FILE, "Thumbs.db"),
        ("data/Thumbs.db", HintKind.EMPTY, None),
    ]
    assert found[2].related_paths == ("b/a.csv",)
