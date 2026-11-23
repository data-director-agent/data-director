"""The core requirements of a Data Management Plan."""

from __future__ import annotations

from dd_dmp_template import SECTIONS


def test_there_are_six_requirements_with_unique_ids_and_headings() -> None:
    assert len(SECTIONS) == 6
    assert len({s.id for s in SECTIONS}) == 6
    assert len({s.heading for s in SECTIONS}) == 6


def test_each_requirement_has_a_summary_and_questions() -> None:
    for section in SECTIONS:
        assert section.summary
        assert section.questions
        assert all(q.endswith("?") for q in section.questions)
