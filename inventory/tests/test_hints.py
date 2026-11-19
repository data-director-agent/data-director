"""The hints for a person, judged from an inventory's names, sizes and digests (#449), and what a
drafter leaves out or asks about because of them (#1072)."""

from __future__ import annotations

from typing import Any

from dd_inventory.hints import (
    DECIDE,
    LEAVE_OUT,
    HintKind,
    deposit_hints,
    file_hints,
    load_rules,
)


def entry(path: str, size: int = 10, digest: str | None = None, *fields: str) -> dict[str, Any]:
    return {
        "file_path": path,
        "file_size": size,
        "file_sha256": digest or path,
        "file_fields": [{"name": f} for f in fields],
    }


FILES = [
    entry("data/readings.csv", 10, "a", "site", "value"),
    entry("data/old/readings (copy).csv", 10, "a", "site", "value"),
    entry("data/Thumbs.db", 0, "e"),
    entry("data/empty.csv", 0, "e"),
    entry("calibration/sites.csv", 10, "b", "node", "lat", "lon"),
    entry("reference/station_hourly.csv", 10, "c"),
    entry("notes/fieldnotes.txt", 10, "d"),
    entry("analysis/plot.R", 10, "f"),
]


def test_every_rule_kind_is_a_hint_kind_and_is_drafted_one_way() -> None:
    kinds = {rule.kind for rule in load_rules()}
    assert kinds == set(HintKind)
    assert set(HintKind) == LEAVE_OUT | DECIDE
    assert not LEAVE_OUT & DECIDE


def test_hints_are_given_in_the_order_of_the_files() -> None:
    hints = file_hints(FILES)
    order = [f["file_path"] for f in FILES]
    positions = [order.index(h.path) for h in hints]
    assert positions == sorted(positions)
    by_kind = {(h.path, h.kind) for h in hints}
    assert ("data/old/readings (copy).csv", HintKind.DUPLICATE) in by_kind
    assert ("data/readings.csv", HintKind.DUPLICATE) in by_kind
    assert ("data/Thumbs.db", HintKind.SYSTEM_FILE) in by_kind
    assert ("data/empty.csv", HintKind.EMPTY) in by_kind
    assert ("calibration/sites.csv", HintKind.COORDINATES) in by_kind
    assert ("reference/station_hourly.csv", HintKind.THIRD_PARTY) in by_kind
    assert ("notes/fieldnotes.txt", HintKind.FREE_TEXT) in by_kind
    assert not [h for h in hints if h.path == "analysis/plot.R"]
    # Two empty files share a digest but are not copies: an empty file is asked about as empty.
    assert not [h for h in hints if h.kind == HintKind.DUPLICATE and h.path.endswith(".db")]


def test_a_draft_leaves_out_one_of_each_set_of_copies_and_asks_about_the_rest() -> None:
    hinted = deposit_hints(FILES)
    assert set(hinted.leave_out) == {
        "data/old/readings (copy).csv",
        "data/Thumbs.db",
        "data/empty.csv",
    }
    assert set(hinted.decide) == {
        "calibration/sites.csv",
        "reference/station_hourly.csv",
        "notes/fieldnotes.txt",
    }
    # The copy kept is not left out, and names the copy it is kept in place of.
    assert "data/readings.csv" not in hinted.leave_out
    (copy,) = hinted.leave_out["data/old/readings (copy).csv"]
    assert copy.related_paths == ("data/readings.csv",)
    for hints in (*hinted.leave_out.values(), *hinted.decide.values()):
        assert all(h.question for h in hints)


def test_a_file_left_out_is_not_also_asked_about() -> None:
    files = [entry("reference/Thumbs.db", 10, "x")]
    hinted = deposit_hints(files)
    assert set(hinted.leave_out) == {"reference/Thumbs.db"}
    assert not hinted.decide


def test_no_hint_no_change() -> None:
    hinted = deposit_hints([entry("data/readings.csv", 10, "a", "site")])
    assert not hinted.leave_out and not hinted.decide
