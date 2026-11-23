"""ISSNs are checked, the registry is built reproducibly from snapshot parts, and a journal is
found by any of its ISSNs or by its title."""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import Any

import pytest

from dd_journals import Journal, PinError, Registry, fold, normal_issn, valid_issn
from dd_journals.build import build
from dd_journals.records import from_openalex
from dd_journals.snapshot import Pin, fetch, problem, update_pin


def source(oid: str, issn_l: str | None, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{oid}",
        "type": "journal",
        "issn_l": issn_l,
        "issn": [issn_l] if issn_l else [],
        "display_name": title,
        "alternate_titles": [],
        "host_organization_name": None,
        "country_code": None,
        "homepage_url": None,
        "is_in_doaj": False,
        "is_oa": False,
        "works_count": 0,
        **extra,
    }


STOTEN = source(
    "S1",
    "0048-9697",
    "Science of The Total Environment",
    issn=["0048-9697", "1879-1026"],
    host_organization_name="Elsevier BV",
    works_count=90000,
)
NATURE = source("S2", "0028-0836", "Nature", issn=["0028-0836", "1476-4687"], works_count=400000)
NATURE_ENV = source("S3", "1758-678X", "Nature Climate Change", works_count=5000)
SCIDATA = source(
    "S4", "2052-4463", "Scientific Data", alternate_titles=["Sci Data"], is_oa=True, is_in_doaj=True
)
# A second OpenAlex record for STOTEN's ISSN-L, with fewer works and one more ISSN.
STOTEN_AGAIN = source("S9", "0048-9697", "Sci Total Environ", issn=["0048-9697", "0000-0000"])
REPOSITORY = {**source("S5", "1234-5679", "Not a journal"), "type": "repository"}
NO_ISSN = source("S6", None, "Journal without an ISSN")

PARTS = [[STOTEN, NATURE, REPOSITORY], [NATURE_ENV, NO_ISSN], [SCIDATA, STOTEN_AGAIN]]


def gz(records: list[dict[str, Any]]) -> bytes:
    return gzip.compress("".join(json.dumps(r) + "\n" for r in records).encode(), mtime=0)


def write_parts(where: Path, parts: list[list[dict[str, Any]]]) -> list[Path]:
    paths = []
    for n, records in enumerate(parts):
        path = where / f"part_{n:04d}.gz"
        path.write_bytes(gz(records))
        paths.append(path)
    return paths


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    data, _ = build(write_parts(tmp_path, PARTS))
    (tmp_path / "journals.jsonl").write_bytes(data)
    return Registry.load(tmp_path / "journals.jsonl")


# --- ISSNs ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "written"),
    [("1879102x", "1879-102X"), (" 0048-9697 ", "0048-9697"), ("0048-969", None), ("", None)],
)
def test_an_issn_is_written_one_way(given: str, written: str | None) -> None:
    assert normal_issn(given) == written


@pytest.mark.parametrize("issn", ["0048-9697", "1758-678X", "20524463", "0028-0836"])
def test_an_issn_with_the_right_check_digit_is_valid(issn: str) -> None:
    assert valid_issn(issn) == normal_issn(issn)


@pytest.mark.parametrize("issn", ["0048-9698", "1758-6781", "abcd-efgh"])
def test_an_issn_with_the_wrong_check_digit_is_not(issn: str) -> None:
    assert valid_issn(issn) is None


# --- building ---------------------------------------------------------------------------------


def test_only_journals_with_an_issn_l_are_kept() -> None:
    assert from_openalex(REPOSITORY) is None
    assert from_openalex(NO_ISSN) is None
    journal = from_openalex(STOTEN)
    assert journal is not None
    assert journal.issn_l in journal.issns
    assert journal.issn_l in journal.portal_url


def test_the_same_parts_build_the_same_bytes_in_any_order(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, count = build(write_parts(tmp_path / "a", PARTS))
    second, _ = build(write_parts(tmp_path / "b", list(reversed(PARTS))))
    assert first == second
    lines = [json.loads(line) for line in first.decode().splitlines()]
    issn_ls = [line["issn_l"] for line in lines]
    assert len(lines) == count
    assert issn_ls == sorted(set(issn_ls))


def test_two_records_for_one_issn_l_become_one_journal(registry: Registry) -> None:
    journal = registry.get("0048-9697")
    assert journal is not None
    assert journal.openalex_id.endswith("S1")
    assert {"0000-0000", "1879-1026"} <= set(journal.issns)


def test_a_journal_survives_its_line(registry: Registry) -> None:
    journal = registry.get("2052-4463")
    assert journal is not None
    assert Journal.from_dict(json.loads(json.dumps(journal.as_dict()))) == journal


# --- looking up -------------------------------------------------------------------------------


def test_any_issn_finds_the_journal(registry: Registry) -> None:
    by_print, by_online = registry.get("0028-0836"), registry.get("14764687")
    assert by_print is not None
    assert by_print == by_online
    assert registry.get("9999-9999") is None
    assert registry.get("not an issn") is None


def test_folding_sets_case_accents_punctuation_and_a_leading_the_aside() -> None:
    assert fold("The Science & Total Environment!") == fold("science and total environment")
    assert fold("Revue d'Écologie") == fold("revue d ecologie")
    assert fold("The") == "the"


def test_search_puts_the_same_title_first_then_a_prefix_then_words(registry: Registry) -> None:
    found = [j.issn_l for j in registry.search("Nature")]
    assert found[0] == registry.get("0028-0836").issn_l  # type: ignore[union-attr]
    assert set(found) == {"0028-0836", "1758-678X"}
    words = registry.search("total science")
    assert [j.issn_l for j in words] == ["0048-9697"]


def test_search_finds_alternate_titles_and_issns(registry: Registry) -> None:
    assert [j.issn_l for j in registry.search("sci data")] == ["2052-4463"]
    assert [j.issn_l for j in registry.search("1879-1026")] == ["0048-9697"]


def test_search_is_the_same_every_time_and_respects_its_limit(registry: Registry) -> None:
    assert registry.search("n") == registry.search("n")
    assert len(registry.search("n", limit=1)) == 1
    assert registry.search("") == []
    assert registry.search("nothing like this") == []


def test_a_registry_that_does_not_match_its_pin_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "journals.jsonl"
    with pytest.raises(PinError):
        Registry.load(path)
    path.write_text("")
    with pytest.raises(PinError):
        Registry.load(path, sha256="0" * 64)


# --- fetching ---------------------------------------------------------------------------------

BUCKET = "https://openalex.s3.amazonaws.com/"


class FakeBucket:
    """OpenAlex's bucket: a manifest and the gzipped parts it names. Counts each request."""

    def __init__(self, parts: list[list[dict[str, Any]]]) -> None:
        self.files = {
            f"{BUCKET}data/jsonl/sources/part_{n:04d}.gz": gz(r) for n, r in enumerate(parts)
        }
        manifest = {
            "date": "2026-10-14",
            "entities": [
                {"entity": "works", "files": []},
                {
                    "entity": "sources",
                    "files": [
                        {
                            "url": url.replace(BUCKET, "s3://openalex/"),
                            "meta": {"content_length": len(body), "record_count": 1},
                        }
                        for url, body in self.files.items()
                    ],
                },
            ],
        }
        self.files[f"{BUCKET}data/jsonl/manifest.json"] = json.dumps(manifest).encode()
        self.asked: list[str] = []

    def __call__(self, url: str) -> io.BytesIO:
        self.asked.append(url)
        if url not in self.files:
            raise OSError(f"404 {url}")
        return io.BytesIO(self.files[url])


def test_a_pin_is_taken_then_fetched_from_the_cache(tmp_path: Path) -> None:
    bucket = FakeBucket(PARTS)
    where = {"cache_dir": tmp_path / "cache", "registry": tmp_path / "j.jsonl"}
    manifest = tmp_path / "manifest.json"
    pin = update_pin(**where, manifest=manifest, opener=bucket)
    assert pin.snapshot_date in pin.label
    assert all(p.sha256 and p.url.startswith(BUCKET) for p in pin.parts)
    assert Pin.load(manifest) == pin
    assert problem(where["registry"], manifest) is None

    built = where["registry"].read_bytes()
    where["registry"].unlink()
    assert problem(where["registry"], manifest) is not None
    bucket.asked.clear()
    fetch(**where, manifest=manifest, opener=bucket)
    assert bucket.asked == []  # every part came from the cache
    assert where["registry"].read_bytes() == built


def test_a_part_that_does_not_match_its_pin_is_refused(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    where = {"registry": tmp_path / "j.jsonl", "manifest": manifest}
    update_pin(cache_dir=tmp_path / "first", **where, opener=FakeBucket(PARTS))
    changed = FakeBucket([[NATURE], [], []])
    with pytest.raises(PinError):
        fetch(cache_dir=tmp_path / "second", **where, opener=changed)
    assert not list((tmp_path / "second").glob("*.part"))


def test_an_unreachable_bucket_is_a_pin_error(tmp_path: Path) -> None:
    def down(url: str) -> io.BytesIO:
        raise OSError("connection refused")

    with pytest.raises(PinError):
        update_pin(tmp_path, tmp_path / "j.jsonl", tmp_path / "m.json", opener=down)
