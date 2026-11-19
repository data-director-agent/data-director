"""A person's key is sealed at rest, and opens only for its own record under the broker's
key-encryption key (docs/specs/model-accounts.md, invariant 2)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dd_broker.seal import Sealed, SealError, seal, unseal
from dd_broker.store import Store

KEY = "sk-ant-seal-test-9e41"


def test_a_sealed_key_opens_for_its_own_record() -> None:
    kek = os.urandom(32)
    assert unseal(kek, "p-1", seal(kek, "p-1", KEY)) == KEY


def test_two_seals_of_one_key_differ() -> None:
    kek = os.urandom(32)
    assert seal(kek, "p-1", KEY) != seal(kek, "p-1", KEY)


def test_a_sealed_key_moved_to_another_record_does_not_open() -> None:
    kek = os.urandom(32)
    with pytest.raises(SealError):
        unseal(kek, "p-2", seal(kek, "p-1", KEY))


def test_a_sealed_key_does_not_open_under_another_key_encryption_key() -> None:
    with pytest.raises(SealError):
        unseal(os.urandom(32), "p-1", seal(os.urandom(32), "p-1", KEY))


def test_an_altered_sealed_key_does_not_open() -> None:
    kek = os.urandom(32)
    sealed = seal(kek, "p-1", KEY)
    altered = Sealed(sealed.nonce, bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:])
    with pytest.raises(SealError):
        unseal(kek, "p-1", altered)


def test_a_key_encryption_key_of_the_wrong_length_is_refused() -> None:
    with pytest.raises(SealError):
        seal(os.urandom(16), "p-1", KEY)


def test_the_store_keeps_the_key_sealed_and_erases_it_at_once(tmp_path: Path) -> None:
    store = Store(tmp_path / "broker.sqlite3", os.urandom(32))
    store.put("p-1", "anthropic", KEY, label="anthropic …9e41")

    account = store.account("p-1")
    assert account is not None and account.key == KEY
    assert KEY not in repr(account)
    for path in tmp_path.iterdir():
        assert KEY.encode() not in path.read_bytes()

    assert store.remove("p-1")
    assert store.account("p-1") is None
    assert not store.remove("p-1")


def test_a_store_opened_with_another_key_encryption_key_opens_no_key(tmp_path: Path) -> None:
    Store(tmp_path / "broker.sqlite3", os.urandom(32)).put("p-1", "anthropic", KEY, label="x")
    with pytest.raises(SealError):
        Store(tmp_path / "broker.sqlite3", os.urandom(32)).account("p-1")
