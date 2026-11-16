"""The text of a PDF, for policies published as one. The only importer of `pypdf`
(docs/specs/dependencies.md).

Its fallback is to read no text: `text` returns None for a PDF it cannot read, or if `pypdf`
cannot be imported, and the agent then reports the policy as unreadable, with its record's
obligations standing as they are.
"""

from __future__ import annotations

import io
import logging

# Pages read from one PDF. A policy longer than this is read in part, and the reading says so.
MAX_PAGES = 60

log = logging.getLogger(__name__)


def text(data: bytes) -> tuple[str, bool] | None:
    """The PDF's text, page by page, and whether pages were left out; None if it has none that
    can be read."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError:  # the fallback the dependency register names
        log.warning("pypdf is not installed; a policy published as PDF is not read")
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return None
        pages = reader.pages
        read = [page.extract_text() or "" for page in pages[:MAX_PAGES]]
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
        log.info("a PDF could not be read: %s", exc)
        return None
    joined = "\n\n".join(p.strip() for p in read if p.strip())
    return (joined, len(pages) > MAX_PAGES) if joined else None
