"""Reading title, abstract and keywords out of README prose (§8).

Worth testing despite being small, because `retrieve` puts the title and abstract into registry
queries as free text. A mistake here is not cosmetic — it surfaces later as a retrieval mistake,
which is exactly the confusion §6.1's derivation fields exist to prevent.
"""

from __future__ import annotations

from pathlib import Path

from standards_advisor.planning import ParsedReadme, read_readme
from tests.conftest import PLANNED_README


def _write(tmp_path: Path, text: str) -> ParsedReadme:
    path = tmp_path / "README.md"
    path.write_text(text, encoding="utf-8")
    return read_readme(path)


def test_the_sample_readme_yields_a_title_abstract_and_keywords():
    parsed = read_readme(PLANNED_README)
    assert parsed.title is not None
    assert parsed.title.startswith("Upland grassland restoration monitoring")
    assert parsed.abstract is not None
    assert "monitor soil and vegetation recovery" in parsed.abstract
    assert "upland grassland" in parsed.keywords
    assert parsed.error is None


def test_the_abstract_stops_at_the_next_heading(tmp_path):
    """Otherwise a project description runs into the installation instructions."""
    parsed = _write(
        tmp_path,
        "# A title\n\nThe real description.\n\n## Installation\n\nRun the thing.\n",
    )
    assert parsed.abstract == "The real description."


def test_the_keywords_line_is_not_swallowed_into_the_abstract(tmp_path):
    parsed = _write(tmp_path, "# T\n\nProse here.\n\nKeywords: one, two, three\n")
    assert parsed.keywords == ["one", "two", "three"]
    assert parsed.abstract == "Prose here."


def test_a_setext_title_is_recognised(tmp_path):
    parsed = _write(tmp_path, "A title\n=======\n\nSome prose.\n")
    assert parsed.title == "A title"
    assert parsed.abstract == "Some prose."


def test_prose_under_a_description_heading_is_used(tmp_path):
    """The other common R5 shape: a title, then metadata, then `## Description`."""
    parsed = _write(
        tmp_path,
        "# T\n\n## Description\n\nWhat the project is.\n\n## Licence\n\nCC-BY.\n",
    )
    assert parsed.abstract == "What the project is."


def test_a_long_readme_is_truncated_and_says_so(tmp_path):
    """The abstract reaches a registry query, so a silent prefix would be unaccountable."""
    parsed = _write(tmp_path, "# T\n\n" + ("word " * 2000))
    assert parsed.abstract is not None
    assert len(parsed.abstract) <= 2000
    assert parsed.notes


def test_a_readme_without_the_conventions_yields_less_not_something_wrong(tmp_path):
    parsed = _write(tmp_path, "just some text with no heading at all\n")
    assert parsed.title is None
    assert parsed.keywords == []
    assert parsed.error is None


def test_a_missing_readme_is_reported_not_raised(tmp_path):
    parsed = read_readme(tmp_path / "absent.md")
    assert parsed.error is not None
    assert parsed.title is None
