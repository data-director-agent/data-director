"""A project keeps a Word document or a text-layer PDF as the file and the text read from it inside
the deployment (docs/specs/projects.md, Documentation; #961)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.projects import (
    SOURCE_MAX_BYTES,
    ProjectError,
    ProjectStore,
    read_document_file,
)
from dd_harness.projects.extract import DOCX, PDF, extract_text
from dd_harness.testing import TEST_PRINCIPAL
from dd_harness.testing.documents import PROTOCOL, encrypted_pdf, pdf_file, word_file

pytestmark = pytest.mark.requirement("C13.3")


def test_the_text_of_a_word_document_is_read_with_its_tables() -> None:
    text = extract_text(DOCX, word_file())
    assert PROTOCOL in text
    assert "depth\tcentimetres" in text


def test_the_text_layer_of_a_pdf_is_read() -> None:
    assert PROTOCOL in extract_text(PDF, pdf_file())


@pytest.mark.parametrize(
    ("media_type", "data"),
    [
        (PDF, pdf_file(None)),  # a scanned page has no text layer
        (PDF, encrypted_pdf()),
        (PDF, b"not a pdf"),
        (DOCX, b"not a zip"),
        (PDF, b"%PDF-" + b"0" * SOURCE_MAX_BYTES),
        ("application/msword", b"anything"),
    ],
    ids=["no-text", "encrypted", "damaged-pdf", "damaged-docx", "too-large", "other-type"],
)
def test_a_file_that_cannot_be_read_is_refused(media_type: str, data: bytes) -> None:
    with pytest.raises(ProjectError):
        extract_text(media_type, data)


def test_a_file_is_kept_beside_the_text_read_from_it(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="t")
    data = pdf_file()

    digest = store.add_document_file(
        project, "plan.pdf", PDF, data, acted_for=TEST_PRINCIPAL, caused_by="t"
    )

    [summary] = store.documentation(project)
    assert summary["documentation_digest"] == digest
    assert summary["documentation_media_type"] == "text/plain"
    assert summary["documentation_source_media_type"] == PDF
    assert PROTOCOL in (store.documentation_text(project, digest) or "")
    assert store.documentation_source(project, digest) == (data, PDF)


def test_a_document_attached_as_text_has_no_file(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="t")
    digest = store.add_documentation(
        project, "notes.md", "text/markdown", PROTOCOL, acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    [summary] = store.documentation(project)
    assert "documentation_source_media_type" not in summary
    assert store.documentation_source(project, digest) is None


def test_a_file_that_is_refused_leaves_no_trace(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="t")
    before = store.events(project)
    with pytest.raises(ProjectError):
        store.add_document_file(
            project, "scan.pdf", PDF, pdf_file(None), acted_for=TEST_PRINCIPAL, caused_by="t"
        )
    assert store.events(project) == before
    assert store.documentation(project) == []


def test_a_file_is_refused_under_a_name_with_a_folder() -> None:
    with pytest.raises(ProjectError):
        read_document_file("plans/plan.pdf", PDF, pdf_file())
