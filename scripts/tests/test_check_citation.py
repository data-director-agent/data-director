"""The rule in scripts/check_citation.py that everyone who writes a commit is a cited author."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_citation as cc  # noqa: E402

AUTHORS = [
    {"given-names": "Ada", "family-names": "Lovelace", "email": "ada@example.org"},
    {"given-names": "Grace", "family-names": "Hopper"},
    {"name": "The Example Consortium"},
]


def test_matched_by_email_whatever_the_name() -> None:
    assert cc.missing({"A. Lovelace <Ada@Example.org>"}, AUTHORS) == []


def test_matched_by_full_name_whatever_the_email() -> None:
    assert cc.missing({"grace hopper <grace@navy.example>"}, AUTHORS) == []


def test_matched_by_name_of_an_entity() -> None:
    assert cc.missing({"The Example Consortium <info@example.net>"}, AUTHORS) == []


def test_unlisted_people_are_reported_in_order() -> None:
    people = {"Zed Nobody <zed@example.org>", "Alan Turing <alan@example.org>"}
    assert cc.missing(people, AUTHORS) == [
        "Alan Turing <alan@example.org>",
        "Zed Nobody <zed@example.org>",
    ]


def test_part_of_a_name_is_not_a_match() -> None:
    assert cc.missing({"Ada <ada@elsewhere.example>"}, AUTHORS) == ["Ada <ada@elsewhere.example>"]


def test_bots_and_assistants_are_not_authors() -> None:
    assert cc.is_bot("dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>")
    assert cc.is_bot("Claude Opus 5.5 <noreply@anthropic.com>")
    assert not cc.is_bot("Ada Lovelace <ada@example.org>")
