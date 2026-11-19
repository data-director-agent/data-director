"""The text of an attached Word or PDF document, read inside the deployment (docs/specs/projects.md,
Documentation). The only importer of `pypdf` and `python-docx` in the harness
(docs/specs/dependencies.md).

A researcher may attach a document about their data as the file they already have it in: a Word
document or a PDF with a text layer. The project keeps the file and the text read from it here;
agents are given the text, as for a document attached as text. A file this module cannot read is a
content problem, refused with a `ProjectError` before anything is kept: an encrypted or damaged
file, a scanned PDF with no text layer (no OCR is attempted), or one whose text is blank or over
`DOCUMENTATION_MAX_BYTES`. If a library cannot be imported, its kind of file is refused, saying
the deployment cannot read it.
"""

from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import Iterator
from typing import Final

from dd_harness.projects.rules import ProjectError

DOCX: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF: Final = "application/pdf"
# The kinds of original file a project keeps beside the text read from it.
SOURCE_MEDIA_TYPES: Final = (DOCX, PDF)
# The largest original file kept, in bytes: what a request through the deployment's proxy can
# carry once encoded (deploy/nginx/data-director.conf), and more than a plan or policy needs.
SOURCE_MAX_BYTES: Final = 1024 * 1024
_KIND: Final = {DOCX: "Word document", PDF: "PDF"}

log = logging.getLogger(__name__)


def extract_text(media_type: str, data: bytes) -> str:
    """The text of the Word or PDF file `data`. Raises `ProjectError` for a file the project
    would not keep: one of another kind, over `SOURCE_MAX_BYTES`, unreadable, or with no text."""
    if media_type not in SOURCE_MEDIA_TYPES:
        raise ProjectError(
            f"a document read from a file is a Word document or a PDF, not {media_type!r}"
        )
    if len(data) > SOURCE_MAX_BYTES:
        raise ProjectError(
            f"a {_KIND[media_type]} may be at most {SOURCE_MAX_BYTES} bytes, not {len(data)}"
        )
    text = _pdf(data) if media_type == PDF else _docx(data)
    if not text.strip():
        raise ProjectError(
            f"this {_KIND[media_type]} holds no text to read"
            + (
                ": a scanned PDF is not read, as no text is recognised in images"
                if media_type == PDF
                else ""
            )
        )
    return text


def _pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError:  # the fallback the dependency register names
        raise ProjectError("this deployment cannot read PDFs") from None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ProjectError("this PDF is encrypted, so it cannot be read")
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
        log.info("a PDF could not be read: %s", exc)
        raise ProjectError("this PDF could not be read") from None
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _docx(data: bytes) -> str:
    try:
        import docx
        from docx.table import Table
    except ImportError:  # the fallback the dependency register names
        raise ProjectError("this deployment cannot read Word documents") from None
    try:
        document = docx.Document(io.BytesIO(data))
        blocks = list(_blocks(document.iter_inner_content(), Table))
    except (zipfile.BadZipFile, ValueError, KeyError, OSError) as exc:
        log.info("a Word document could not be read: %s", exc)
        raise ProjectError("this Word document could not be read") from None
    return "\n\n".join(b for b in blocks if b.strip())


def _blocks(content: Iterator[object], table_type: type) -> Iterator[str]:
    """Each paragraph's text, and each table's rows with their cells separated by tabs, in the
    order the document has them."""
    for block in content:
        if isinstance(block, table_type):
            rows = block.rows  # type: ignore[attr-defined]
            yield "\n".join("\t".join(cell.text.strip() for cell in row.cells) for row in rows)
        else:
            yield block.text  # type: ignore[attr-defined]
