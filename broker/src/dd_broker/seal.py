"""Sealing a person's key at rest (docs/specs/model-accounts.md, invariant 2).

Each key is encrypted with AES-256-GCM under the broker's key-encryption key, which only the
broker's process reads, from a systemd credential. A fresh 96-bit nonce is drawn for every seal.
The record's pseudonym is bound to the ciphertext as associated data, so a sealed key copied into
another person's record does not open. A database copy without the key-encryption key opens no
key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENCRYPTION_KEY_BYTES = 32
NONCE_BYTES = 12
# Versioned, so a later scheme can be told apart from this one.
_AAD_PREFIX = b"dd-model-broker/seal/v1\0"


class SealError(Exception):
    """A sealed key does not open: wrong key-encryption key, wrong record or altered bytes. The
    message never contains a key."""


@dataclass(frozen=True)
class Sealed:
    nonce: bytes
    ciphertext: bytes


def _aad(pseudonym: str) -> bytes:
    return _AAD_PREFIX + pseudonym.encode("utf-8")


def _cipher(key_encryption_key: bytes) -> AESGCM:
    if len(key_encryption_key) != KEY_ENCRYPTION_KEY_BYTES:
        raise SealError(f"the key-encryption key is not {KEY_ENCRYPTION_KEY_BYTES} bytes")
    return AESGCM(key_encryption_key)


def seal(key_encryption_key: bytes, pseudonym: str, secret: str) -> Sealed:
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _cipher(key_encryption_key).encrypt(nonce, secret.encode("utf-8"), _aad(pseudonym))
    return Sealed(nonce=nonce, ciphertext=ciphertext)


def unseal(key_encryption_key: bytes, pseudonym: str, sealed: Sealed) -> str:
    try:
        plain = _cipher(key_encryption_key).decrypt(
            sealed.nonce, sealed.ciphertext, _aad(pseudonym)
        )
    except InvalidTag:
        raise SealError("a sealed key does not open for this record") from None
    return plain.decode("utf-8")
