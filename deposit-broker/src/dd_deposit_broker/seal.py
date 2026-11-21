"""Sealing a person's repository token at rest.

Each token is encrypted with AES-256-GCM under the deposit broker's key-encryption key, which only
its process reads, from a systemd credential. A fresh 96-bit nonce is drawn for every seal. The
record's pseudonym and the repository's API root are bound to the ciphertext as associated data, so
a sealed token copied into another person's record, or another repository's, does not open.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENCRYPTION_KEY_BYTES = 32
NONCE_BYTES = 12
# Versioned, and not the model broker's, so neither opens the other's records.
_AAD_PREFIX = b"dd-deposit-broker/seal/v1\0"


class SealError(Exception):
    """A sealed token does not open. The message never contains a token."""


@dataclass(frozen=True)
class Sealed:
    nonce: bytes
    ciphertext: bytes


def _aad(pseudonym: str, base_url: str) -> bytes:
    return _AAD_PREFIX + pseudonym.encode("utf-8") + b"\0" + base_url.encode("utf-8")


def _cipher(key_encryption_key: bytes) -> AESGCM:
    if len(key_encryption_key) != KEY_ENCRYPTION_KEY_BYTES:
        raise SealError(f"the key-encryption key is not {KEY_ENCRYPTION_KEY_BYTES} bytes")
    return AESGCM(key_encryption_key)


def seal(key_encryption_key: bytes, pseudonym: str, base_url: str, secret: bytes) -> Sealed:
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _cipher(key_encryption_key).encrypt(nonce, secret, _aad(pseudonym, base_url))
    return Sealed(nonce=nonce, ciphertext=ciphertext)


def unseal(key_encryption_key: bytes, pseudonym: str, base_url: str, sealed: Sealed) -> bytes:
    try:
        return _cipher(key_encryption_key).decrypt(
            sealed.nonce, sealed.ciphertext, _aad(pseudonym, base_url)
        )
    except InvalidTag:
        raise SealError("a sealed token does not open for this record") from None
