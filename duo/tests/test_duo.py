"""The pinned DUO release loads whole, matches its manifest, and names a data use condition."""

import hashlib
import importlib.util
from importlib import resources
from pathlib import Path
from types import ModuleType

import pytest

import dd_duo
from dd_duo import lookup, release, terms
from dd_duo.duo import PinError, _terms

HERE = Path(__file__).resolve().parent


def _pin_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pin_duo", HERE.parent / "scripts" / "pin_duo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_release_says_where_it_comes_from_and_matches_its_pin() -> None:
    pinned = release()
    assert all([pinned.version, pinned.file, pinned.licence, pinned.source])
    raw = resources.files("dd_duo").joinpath("data", pinned.file).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pinned.sha256


def test_every_term_is_a_permission_or_modifier_with_a_persistent_iri() -> None:
    every = terms()
    assert every
    ids = [t.id for t in every]
    assert len(set(ids)) == len(ids) and ids == sorted(ids)
    for term in every:
        assert term.kind in ("permission", "modifier")
        assert term.label and term.definition
        assert term.url.endswith(term.id.replace(":", "_"))
    assert terms("permission") and terms("modifier")
    assert {t.kind for t in terms("modifier")} == {"modifier"}


def test_a_term_is_found_by_identifier_or_shorthand() -> None:
    irb = lookup("DUO:0000021")
    assert irb is not None and irb.shorthand
    assert lookup(irb.shorthand) == irb
    assert lookup(irb.shorthand.lower()) == irb


def test_an_unknown_name_gives_nothing() -> None:
    assert lookup("DUO:9999999") is None
    assert lookup("not a term") is None


def test_a_term_is_stored_as_it_reads() -> None:
    term = terms()[0]
    assert set(term.as_dict()) == {
        "id",
        "shorthand",
        "label",
        "definition",
        "kind",
        "parent",
        "url",
    }


def test_damaged_data_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _terms.cache_clear()
    monkeypatch.setattr(dd_duo.duo, "_read", lambda name: b"{}\n" if name.endswith("l") else b"")
    monkeypatch.setattr(
        dd_duo.duo, "release", lambda: dd_duo.Release("x", "x.jsonl", "0" * 64, "x", "x")
    )
    with pytest.raises(PinError):
        _terms()
    _terms.cache_clear()


def test_the_pin_keeps_current_permissions_and_modifiers_only() -> None:
    pin = _pin_script()
    owl = (HERE / "fixtures" / "mini.owl").read_bytes()
    kept = {r["id"]: r for r in pin.records(owl)}
    # The roots, an obsolete term and a research type that is neither are left out.
    assert set(kept) == {"DUO:0000006", "DUO:0000021", "DUO:0000042"}
    assert kept["DUO:0000006"]["kind"] == "permission"
    assert kept["DUO:0000006"]["parent"] == "DUO:0000042"
    assert kept["DUO:0000021"]["kind"] == "modifier"
    assert pin.records(owl) == pin.records(owl)
