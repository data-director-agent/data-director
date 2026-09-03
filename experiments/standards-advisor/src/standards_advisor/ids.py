"""Run identifiers, content fingerprints and text hashes.

The content fingerprint is computed and recorded from the first commit even though nothing
consumes it yet. C17's caching (skip work whose input has not changed) is cheap to add later;
retrofitting a fingerprint onto run records that were written without one is not.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from pathlib import Path

# Bytes read from the head of a file when fingerprinting. A fingerprint is for recognising the
# same input again, not for proving a file has not been tampered with, so the head plus the
# total size is enough — and it keeps fingerprinting a large file cheap.
FINGERPRINT_HEAD_BYTES = 1 << 20  # 1 MiB


def utc_now() -> datetime:
    """Timezone-aware UTC. The only place the current time is read."""
    return datetime.now(tz=UTC)


def new_run_id() -> str:
    """A sortable, collision-resistant run identifier.

    Sortable matters: `runs/` is browsed by a human, and lexical order being chronological order
    is worth more here than a shorter string.
    """
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file_head(path: Path, head_bytes: int = FINGERPRINT_HEAD_BYTES) -> tuple[str, int]:
    """Return `(digest, size_bytes)` for a file, hashing at most `head_bytes` of content.

    The size is folded into the digest so two files sharing a first megabyte but differing in
    length do not share a fingerprint.
    """
    size = path.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    digest.update(b"\0")
    with path.open("rb") as handle:
        digest.update(handle.read(head_bytes))
    return digest.hexdigest(), size
