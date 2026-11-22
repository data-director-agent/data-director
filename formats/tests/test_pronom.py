"""The pinned PRONOM release loads whole, matches its manifest, and describes a PUID."""

import hashlib
from importlib import resources

from dd_formats import lookup, records, release


def test_the_release_says_where_it_comes_from_and_matches_its_pin() -> None:
    pinned = release()
    assert pinned.version > 0
    assert all([pinned.created, pinned.file, pinned.licence, pinned.source])
    raw = resources.files("dd_formats").joinpath("data", pinned.file).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pinned.sha256


def test_every_record_names_its_format_and_links_to_its_page() -> None:
    every = list(records())
    assert every
    puids = [r.puid for r in every]
    assert len(set(puids)) == len(puids)
    for r in every:
        assert r.name and r.puid in r.url
        assert all(e == e.lower() for e in r.extensions)
        assert r.superseded_by is None or r.superseded_by != r.puid


def test_a_puid_gives_its_record() -> None:
    tiff = lookup("fmt/353")
    assert tiff is not None
    assert tiff.puid == "fmt/353"
    assert "image/tiff" in tiff.media_types
    assert "tif" in tiff.extensions


def test_a_deprecated_puid_gives_the_record_that_replaces_it() -> None:
    deprecated = next(r for r in records() if r.superseded_by is not None)
    current = lookup(deprecated.puid)
    assert current is not None
    assert current.puid == deprecated.superseded_by


def test_an_unknown_puid_gives_nothing() -> None:
    assert lookup("fmt/999999") is None
    assert lookup("not a puid") is None


def test_a_record_is_stored_as_it_reads() -> None:
    tiff = lookup("fmt/353")
    assert tiff is not None
    assert tiff.as_dict()["puid"] == "fmt/353"
    assert set(tiff.as_dict()) == {
        "puid",
        "name",
        "version",
        "media_types",
        "extensions",
        "superseded_by",
        "url",
    }
