"""The kinds of files an inventory lists, as the conductor tells an orchestrator them (#1287)."""

from __future__ import annotations

from typing import Any

from dd_harness.project_facts import formats


def file(media_type: str | None, size: int, *ids: str) -> dict[str, Any]:
    found: dict[str, Any] = {"file_size": size, "file_pronom_ids": list(ids)}
    if media_type is not None:
        found["file_media_type"] = media_type
    return found


def test_files_are_grouped_by_media_type_the_most_bytes_first() -> None:
    files = [
        file("text/plain", 5, "x-fmt/111"),
        file("text/csv", 100, "x-fmt/18"),
        file("text/csv", 100, "x-fmt/18", "fmt/1000"),
        file(None, 1),
        file("text/plain", 5, "x-fmt/111"),
    ]
    assert formats(files) == [
        {
            "format_media_type": "text/csv",
            "format_pronom_ids": ["fmt/1000", "x-fmt/18"],
            "format_file_count": 2,
        },
        {
            "format_media_type": "text/plain",
            "format_pronom_ids": ["x-fmt/111"],
            "format_file_count": 2,
        },
        # The files whose media type could not be told are a group of their own.
        {"format_file_count": 1},
    ]


def test_an_inventory_with_no_files_has_no_formats() -> None:
    assert formats([]) == []
