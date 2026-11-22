"""The rule that finds which core requirements a plan's headings cover."""

from __future__ import annotations

import pytest

from dd_dmp_template import SECTIONS, coverage, heading_of, split

PLAN = """# Data Management Plan: a test

Some words before the first section.

## 1. Data collection

We will interview people.

**Storage and backup**

On the university's storage.

3. Ethics and consent

1. We will ask for consent before each interview.

## Sharing and long-term preservation

In a repository.
"""


def test_every_section_has_questions_and_cues_and_a_unique_id() -> None:
    assert len({s.id for s in SECTIONS}) == len(SECTIONS)
    for section in SECTIONS:
        assert section.questions
        assert section.cues
        assert all(cue == cue.lower() for cue in section.cues)


@pytest.mark.parametrize(
    ("line", "heading"),
    [
        ("## 2. Documentation", "2. Documentation"),
        ("**Storage and backup**", "Storage and backup"),
        ("3.1 Backup", "Backup"),
        ("Section 4 Legal requirements:", "Legal requirements"),
        ("1. We will store the data on a server.", None),
        ("An ordinary line of prose", None),
        ("#" + "x" * 200, None),
    ],
)
def test_a_heading_is_found_in_markdown_bold_or_numbered_form(
    line: str, heading: str | None
) -> None:
    assert heading_of(line) == heading


def test_a_plan_is_split_at_its_headings_and_keeps_the_text_before_the_first() -> None:
    passages = split(PLAN)
    assert passages[0].heading == "Data Management Plan: a test"
    assert "before the first section" in passages[0].text
    assert [p.heading for p in passages[1:]] == [
        "1. Data collection",
        "Storage and backup",
        "Ethics and consent",
        "Sharing and long-term preservation",
    ]
    assert "consent before each interview" in passages[3].text


def test_coverage_names_the_sections_a_heading_names_and_leaves_the_rest_uncovered() -> None:
    covered = {c.section.id: c.covered for c in coverage(PLAN)}
    assert covered == {
        "data-collection": True,
        "documentation-quality": False,
        "storage-backup": True,
        "legal-ethical": True,
        "sharing-preservation": True,
        "responsibilities-resources": False,
    }


def test_a_plan_with_no_headings_covers_nothing() -> None:
    assert not any(c.covered for c in coverage("We will look after the data well."))
