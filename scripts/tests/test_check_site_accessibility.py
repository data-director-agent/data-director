"""How scripts/check_site_accessibility.py splits the site's pages between CI's parallel jobs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_site_accessibility as site  # noqa: E402

PAGES = ["", "guide/", "specs/app/", "specs/system/", "glossary/", "404.html", "reviews/"]


def test_every_page_is_in_exactly_one_shard() -> None:
    parts = [site.shard(PAGES, f"{i}/3") for i in (1, 2, 3)]
    checked = [page for part in parts for page in part]
    assert sorted(checked) == sorted(PAGES)
    assert all(parts)


def test_no_shard_keeps_every_page() -> None:
    assert site.shard(PAGES, None) == PAGES


@pytest.mark.parametrize("value", ["0/3", "4/3", "3", "a/b", "1/0"])
def test_a_shard_that_names_no_part_is_refused(value: str) -> None:
    with pytest.raises(ValueError):
        site.shard(PAGES, value)
