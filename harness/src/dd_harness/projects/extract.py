"""The text of an attached Word or PDF document, read inside the deployment (docs/specs/projects.md,
Documentation). The only importer of `pypdf` and `python-docx` in the harness
(docs/specs/dependencies.md).

A researcher may attach a document about their data as the file they already have it in: a Word
document or a PDF with a text layer. The project keeps the file and the text read from it here;
agents are given the text, as for a document attached as text. The text of a Word document is
Markdown, keeping its headings, lists and tables (`extracted_media_type`); a PDF's is plain text,
since its text layer says nothing of its structure. A file this module cannot read is a
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


def extracted_media_type(source_media_type: str) -> str:
    """The media type of the text read from a file of `source_media_type`: Markdown for a Word
    document, whose headings, lists and tables it keeps, and plain text for a PDF."""
    return "text/markdown" if source_media_type == DOCX else "text/plain"


def _docx(data: bytes) -> str:
    try:
        import docx
        from docx.table import Table
    except ImportError:  # the fallback the dependency register names
        raise ProjectError("this deployment cannot read Word documents") from None
    try:
        document = docx.Document(io.BytesIO(data))
        # A document with a title has it as the first level, and its headings beneath it.
        titled = any(p.style is not None and p.style.name == "Title" for p in document.paragraphs)
        blocks = list(_blocks(document.iter_inner_content(), Table, shift=int(titled)))
    except (zipfile.BadZipFile, ValueError, KeyError, OSError) as exc:
        log.info("a Word document could not be read: %s", exc)
        raise ProjectError("this Word document could not be read") from None
    return _joined(b for b in blocks if b.strip())


def _blocks(content: Iterator[object], table_type: type, *, shift: int) -> Iterator[str]:
    """Each paragraph as a line of Markdown, by its style (a heading, a list item or a paragraph),
    and each table as a Markdown table, in the order the document has them. The words are the
    document's own: no emphasis is added, so that a quotation from the text is found in it."""
    for block in content:
        if isinstance(block, table_type):
            yield _table([[cell.text for cell in row.cells] for row in block.rows])  # type: ignore[attr-defined]
        else:
            style = getattr(getattr(block, "style", None), "name", None) or ""
            yield _paragraph(block.text, style, shift)  # type: ignore[attr-defined]


def _paragraph(text: str, style: str, shift: int) -> str:
    """`text` as Markdown for a paragraph of the Word style `style`, its heading levels `shift`
    deeper."""
    text = text.strip()
    if not text:
        return ""
    if style == "Title":
        return f"# {text}"
    if style.startswith("Heading "):
        level = style.removeprefix("Heading ").strip()
        depth = min(max(int(level), 1), 6) if level.isdigit() else 2
        return f"{'#' * min(depth + shift, 6)} {text}"
    if style.startswith(("List Bullet", "List Number")):
        level = style.rsplit(" ", 1)[-1]
        indent = "  " * (int(level) - 1 if level.isdigit() else 0)
        return f"{indent}{'1.' if style.startswith('List Number') else '-'} {text}"
    if style == "List Paragraph":
        return f"- {text}"
    return text


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _table(rows: list[list[str]]) -> str:
    """`rows` as a Markdown table, the first row its header."""
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    cells = [[_cell(c) for c in row] + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(row) + " |" for row in cells]
    lines.insert(1, "|" + " --- |" * width)
    return "\n".join(lines)


def _joined(blocks: Iterator[str]) -> str:
    """The blocks with a blank line between them, except between items of one list."""
    out: list[str] = []
    for block in blocks:
        if out and _is_item(out[-1]) and _is_item(block):
            out.append("\n" + block)
        elif out:
            out.append("\n\n" + block)
        else:
            out.append(block)
    return "".join(out)


def _is_item(block: str) -> bool:
    return block.lstrip().startswith(("- ", "1. "))
