"""`ProjectStorage` checks of the documents a project keeps (docs/specs/projects.md,
Documentation): a document attached as text, kept by the digest of its text and listed once; one
refused, leaving no trace; and a Word document or PDF kept as the file beside the text read from
it. `dd_harness.testing.storage` runs them with every other check. The small Word and PDF files
they use are built in memory, and tests of the app use them too."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import docx
from pypdf import PdfWriter

from dd_harness.projects import (
    DOCUMENTATION_ADDED,
    DOCUMENTATION_MAX_BYTES,
    PROJECT_CREATED,
    ProjectError,
)
from dd_harness.projects.extract import PDF
from dd_harness.storage import ProjectStorage
from dd_harness.testing.fixtures import TEST_PRINCIPAL

MakeProjectStorage = Callable[[str], ProjectStorage]
# A project identifier no store holds.
NOWHERE = "0" * 8 + "-0000-7000-8000-" + "0" * 12

# The text the files below hold.
PROTOCOL = "Soil cores were taken weekly at 10 cm depth."


def word_file() -> bytes:
    """A Word document with a paragraph and a table."""
    document = docx.Document()
    document.add_paragraph(PROTOCOL)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "depth"
    table.rows[0].cells[1].text = "centimetres"
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def pdf_file(text: str | None = PROTOCOL) -> bytes:
    """A one-page PDF whose text layer holds `text`, or a blank page."""
    if text is None:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1))
    out.write(b"startxref\n%d\n%%%%EOF\n" % xref)
    return out.getvalue()


def encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@contextmanager
def _refused(what: str) -> Iterator[None]:
    """Assert that the block raises `ProjectError`; `what` says what should have been refused."""
    try:
        yield
    except ProjectError:
        return
    raise AssertionError(f"{what} was not refused")


def check_documentation_is_kept_by_digest_and_listed_once(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.documentation(project_id) == []

    def add(name: str, text: str, media_type: str = "text/markdown") -> str:
        return store.add_documentation(
            project_id, name, media_type, text, acted_for=TEST_PRINCIPAL, caused_by="check"
        )

    protocol = "# Protocol\n\nSamples were taken weekly.\n"
    digest = add("protocol.md", protocol)
    assert digest == hashlib.sha256(protocol.encode("utf-8")).hexdigest()
    add("codebook.txt", "age: years", "text/plain")
    add("protocol.md", protocol)
    listed = store.documentation(project_id)
    assert [d["documentation_name"] for d in listed] == ["protocol.md", "codebook.txt"]
    assert listed[0]["documentation_digest"] == digest
    assert listed[0]["documentation_size"] == len(protocol.encode("utf-8"))
    assert listed[0]["documentation_media_type"] == "text/markdown"
    assert all("text" not in d for d in listed)
    assert store.documentation_text(project_id, digest) == protocol
    assert store.documentation_text(project_id, "0" * 64) is None
    kinds = [e["event"] for e in store.events(project_id)]
    assert kinds == [PROJECT_CREATED] + [DOCUMENTATION_ADDED] * 3
    assert make("projects").documentation(project_id) == listed


def check_refused_documentation_leaves_no_trace(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    refused = [
        ("data.csv", "text/csv", "a,b\n1,2"),
        ("report.pdf", "application/pdf", "%PDF"),
        ("notes.md", "text/markdown", "  \n"),
        ("big.txt", "text/plain", "x" * (DOCUMENTATION_MAX_BYTES + 1)),
        ("../notes.md", "text/markdown", "notes"),
        ("folder/notes.md", "text/markdown", "notes"),
        ("C:\\notes.md", "text/markdown", "notes"),
        ("", "text/markdown", "notes"),
        ("x" * 256, "text/markdown", "notes"),
    ]
    for name, media_type, text in refused:
        with _refused(f"{name[:20]!r} as {media_type}"):
            store.add_documentation(
                project_id, name, media_type, text, acted_for=TEST_PRINCIPAL, caused_by="check"
            )
    with _refused("a document for an unknown project"):
        store.add_documentation(
            NOWHERE, "notes.md", "text/markdown", "notes", acted_for=TEST_PRINCIPAL, caused_by="c"
        )
    assert [e["event"] for e in store.events(project_id)] == [PROJECT_CREATED]
    assert store.documentation(project_id) == []


def check_a_document_file_is_kept_beside_its_text(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    data = pdf_file()
    digest = store.add_document_file(
        project_id, "plan.pdf", PDF, data, acted_for=TEST_PRINCIPAL, caused_by="check"
    )
    [listed] = store.documentation(project_id)
    assert listed["documentation_media_type"] == "text/plain"
    assert listed["documentation_source_media_type"] == PDF
    assert PROTOCOL in (store.documentation_text(project_id, digest) or "")
    assert store.documentation_source(project_id, digest) == (data, PDF)
    assert make("projects").documentation_source(project_id, digest) == (data, PDF)
    with _refused("a scanned PDF"):
        store.add_document_file(
            project_id, "scan.pdf", PDF, pdf_file(None), acted_for=TEST_PRINCIPAL, caused_by="c"
        )
    assert [e["event"] for e in store.events(project_id)] == [PROJECT_CREATED, DOCUMENTATION_ADDED]


DOCUMENTATION_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "documentation is kept by digest and listed once": (
        check_documentation_is_kept_by_digest_and_listed_once
    ),
    "refused documentation leaves no trace": check_refused_documentation_leaves_no_trace,
    "a document file is kept beside its text": check_a_document_file_is_kept_beside_its_text,
}
