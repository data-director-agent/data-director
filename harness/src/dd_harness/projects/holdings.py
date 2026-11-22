"""What a project holds about its research data: an inventory of its files and the supporting
documents a researcher attached (docs/specs/projects.md).

What a project holds of its research data is a `FileInventory`, never the files. An inventory is
checked against the core class schema before it is added, and kept as its `dd-input-json-v1`
canonical bytes, so its digest is the input hash the conductor records when an agent is given it.

A researcher may attach a supporting document, such as a protocol or a codebook, as text: a
`documentation_added` event names it, its media type and size, and the SHA-256 of its UTF-8
text, under which the text is kept as a blob (`add_documentation`). Only plain text and Markdown
within `DOCUMENTATION_MAX_BYTES` are kept, and a name is a file name, never a path. Attaching the
same text again under the same name records nothing new in `documentation`, which lists each
document once, the one added first first.

A Word document or a PDF with a text layer is kept as the file and the text read from it inside
the deployment (`add_document_file`, `dd_harness.projects.extract`): the text is the document an
agent is given, as plain text, and the event names the file's media type, size and digest too, so
the file can be served beside it (`documentation_source`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from functools import cache
from typing import Any, Final

from dd_harness.projects.extract import extract_text, extracted_media_type
from dd_harness.projects.fold import text_digest
from dd_harness.projects.rules import (
    DOCUMENTATION_ADDED,
    INVENTORY_ADDED,
    ProjectError,
    ProjectRules,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import FileInventory, Principal, inventory_part_problems
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash

# What documentation a project keeps (docs/specs/projects.md): text a person can read, within a
# size a document about the data needs and a dataset rarely fits.
DOCUMENTATION_MEDIA_TYPES: Final = ("text/plain", "text/markdown")
DOCUMENTATION_MAX_BYTES: Final = 256 * 1024
# The longest name a document is kept under, in characters: a file name.
DOCUMENTATION_NAME_MAX_LENGTH: Final = 255


def check_documentation(name: str, media_type: str, text: str) -> None:
    """Raise `ProjectError` for a document the project would not keep (`add_documentation`), so
    that a caller adding more than one thing can refuse all of it before adding any."""
    if media_type not in DOCUMENTATION_MEDIA_TYPES:
        raise ProjectError(
            f"a document is {' or '.join(DOCUMENTATION_MEDIA_TYPES)}, not {media_type!r}"
        )
    _check_documentation_name(name)
    if not text.strip():
        raise ProjectError("a document may not be blank")
    size = len(text.encode("utf-8"))
    if size > DOCUMENTATION_MAX_BYTES:
        raise ProjectError(f"a document may be at most {DOCUMENTATION_MAX_BYTES} bytes, not {size}")


def _check_documentation_name(name: str) -> None:
    """Refuse a document name that is blank, too long, or names a folder."""
    if not name.strip():
        raise ProjectError("a document needs a name")
    if len(name) > DOCUMENTATION_NAME_MAX_LENGTH:
        raise ProjectError(
            f"a document's name may be at most {DOCUMENTATION_NAME_MAX_LENGTH} characters"
        )
    if "/" in name or "\\" in name or name in (".", "..") or any(ord(c) < 32 for c in name):
        raise ProjectError("a document's name is a file name, without any folder")


@cache
def _inventory_schema() -> ClassSchema:
    return ClassSchema.of(FileInventory)


class Holdings(ProjectRules):
    """The rules of what a project holds about its data: its inventory and its documentation."""

    def add_inventory(
        self,
        project_id: str,
        inventory: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a `FileInventory` to the project. Returns its digest. When the project already
        holds one, the event names its digest as `revises`, found in the log, never given.

        Raises `ProjectError` for an unknown project, a document the class schema refuses, or one
        whose parts overlap or leave a file under no part's folder."""
        self._require(project_id)
        document = dict(inventory)
        errors = _inventory_schema().errors(document) or inventory_part_problems(document)
        if errors:
            raise ProjectError(f"not a FileInventory: {'; '.join(errors)}")
        digest = input_hash(document)
        self._keep_blob(project_id, digest, canonicalise(document, INPUT_CANONICALISATION))
        files = document.get("inventory_files") or []
        detail: dict[str, Any] = {
            "digest": digest,
            "canonicalisation": INPUT_CANONICALISATION,
            "file_count": len(files),
            "inventory_made_at": document["inventory_made_at"],
        }
        if parts := document.get("inventory_parts"):
            detail["part_count"] = len(parts)
        with self._section(project_id) as section:
            previous = [e for e in section.events() if e["event"] == INVENTORY_ADDED]
            if previous:
                detail["revises"] = previous[-1]["digest"]
            section.append([self._event(project_id, INVENTORY_ADDED, acted_for, caused_by, detail)])
        return digest

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        """The inventory added last, or None if none has been."""
        return self._latest(project_id, INVENTORY_ADDED)

    def add_documentation(
        self,
        project_id: str,
        name: str,
        media_type: str,
        text: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a supporting document's text to the project. Returns the SHA-256 of its UTF-8 text.

        Raises `ProjectError` for an unknown project, a media type outside
        `DOCUMENTATION_MEDIA_TYPES`, a blank text or one over `DOCUMENTATION_MAX_BYTES`, or a name
        that is blank, too long, or holds a folder. What is refused leaves no trace."""
        self._require(project_id)
        check_documentation(name, media_type, text)
        return self._keep_documentation(project_id, name, media_type, text, acted_for, caused_by)

    def add_document_file(
        self,
        project_id: str,
        name: str,
        media_type: str,
        data: bytes,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a Word document or PDF: the text read from it, as Markdown for a Word document and
        plain text for a PDF (`extracted_media_type`), and the file itself.
        Returns the SHA-256 of the text, as `add_documentation` does. Raises `ProjectError` for
        what `read_document_file` refuses. What is refused leaves no trace."""
        self._require(project_id)
        text = read_document_file(name, media_type, data)
        source = {"source_media_type": media_type, "source_size": len(data)}
        source["source_digest"] = digest = hashlib.sha256(data).hexdigest()
        self._keep_blob(project_id, digest, data)
        return self._keep_documentation(
            project_id, name, extracted_media_type(media_type), text, acted_for, caused_by, source
        )

    def _keep_documentation(
        self,
        project_id: str,
        name: str,
        media_type: str,
        text: str,
        acted_for: Principal,
        caused_by: str,
        source: Mapping[str, Any] | None = None,
    ) -> str:
        content = text.encode("utf-8")
        digest = text_digest(text)
        self._keep_blob(project_id, digest, content)
        detail = {"name": name, "media_type": media_type, "size": len(content), "digest": digest}
        self._append(
            project_id, DOCUMENTATION_ADDED, acted_for, caused_by, {**detail, **(source or {})}
        )
        return digest

    def documentation(self, project_id: str) -> list[dict[str, Any]]:
        """Each document the project holds, without its text, as a `DocumentationSummary`: the
        one added first first, and a name and text added again listed once, when first added.
        Raises `UnknownProjectError` for an unknown project."""
        found: dict[tuple[str, str], dict[str, Any]] = {}
        for event in self.events(project_id):
            if event["event"] != DOCUMENTATION_ADDED:
                continue
            found.setdefault(
                (event["name"], event["digest"]),
                {
                    "documentation_name": event["name"],
                    "documentation_digest": event["digest"],
                    "documentation_media_type": event["media_type"],
                    "documentation_size": event["size"],
                    "documentation_added_at": event["at"],
                    **(
                        {"documentation_source_media_type": event["source_media_type"]}
                        if "source_media_type" in event
                        else {}
                    ),
                },
            )
        return list(found.values())

    def documentation_text(self, project_id: str, digest: str) -> str | None:
        """The text of the project's document with this digest, or None if it holds none.
        Raises `UnknownProjectError` for an unknown project."""
        held = {e["digest"] for e in self.events(project_id) if e["event"] == DOCUMENTATION_ADDED}
        if digest not in held:
            return None
        return self._blob(project_id, digest).decode("utf-8")

    def documentation_source(self, project_id: str, digest: str) -> tuple[bytes, str] | None:
        """The file the project's document with this digest was read from, and its media type,
        or None if it was attached as text or the project holds none. Raises
        `UnknownProjectError` for an unknown project."""
        for event in self.events(project_id):
            kept = event["event"] == DOCUMENTATION_ADDED and event["digest"] == digest
            if kept and "source_digest" in event:
                source = self._blob(project_id, event["source_digest"])
                return source, event["source_media_type"]
        return None


def read_document_file(name: str, media_type: str, data: bytes) -> str:
    """The text of a Word or PDF file the project would keep under `name`, read inside the
    deployment, so that a caller adding more than one thing can refuse all of it before adding
    any. Raises `ProjectError` for a file `extract_text` refuses, or a name or text
    `check_documentation` refuses."""
    _check_documentation_name(name)
    text = extract_text(media_type, data)
    check_documentation(name, "text/plain", text)
    return text
