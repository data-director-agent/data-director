"""The checks before packaging that say where a person acts on what they find
(docs/specs/deposit.md, Validation): the documents a repository requires or recommends, a data
dictionary for tabular data, what the repository fills in itself, and, for each missing field, the
page of the project where its value is supplied. `dd_harness.deposit` runs them with the rest.

Each result names a page of the project in `supplied_on`, from the `SuppliedOn` vocabulary of the
core schema: a document is approved on the documents page, a repository chosen on the repository
page, and a field's value is supplied where its requirement set's `supplied_on` says, on the
documents page (the metadata record's questions) unless it names another.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import replace
from typing import Any, Final

from dd_harness.deposit_report import project_iri
from dd_harness.shacl import DD, INFO, VIOLATION, WARNING, Result, Severity
from dd_sdk.contract.deposit import SuppliedOn
from dd_sdk.contract.models import DocumentKind

DOCUMENT_CHECK = DD + "RequiredDocumentConstraintComponent"
REPOSITORY_CHECK = DD + "RepositoryChoiceConstraintComponent"
FILLED_CHECK = DD + "FilledByRepositoryConstraintComponent"

DOCUMENTS: Final = SuppliedOn.DOCUMENTS.value
REPOSITORY: Final = SuppliedOn.REPOSITORY.value

# The media types of a table, beside an inventory entry whose fields were read as one.
TABULAR: Final = frozenset(
    {
        "text/csv",
        "text/tab-separated-values",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.apache.parquet",
    }
)


def no_repository(project_id: str) -> Result:
    return Result(
        VIOLATION,
        "No repository has been chosen, so there are no requirements to check the project against.",
        project_iri(project_id),
        REPOSITORY_CHECK,
        supplied_on=REPOSITORY,
    )


def resolver_warnings(project_id: str, requirements: Mapping[str, Any]) -> Iterator[Result]:
    """The warnings from resolving the repository choice, each about the choice."""
    for warning in requirements.get("warnings", []):
        yield Result(
            WARNING, warning, project_iri(project_id), REPOSITORY_CHECK, supplied_on=REPOSITORY
        )


def check_documents(
    project_id: str,
    requirements: Mapping[str, Any],
    kinds: Iterable[str],
    inventory: Mapping[str, Any] | None,
) -> Iterator[Result]:
    """Each document kind the set requires (a violation) or recommends (a warning) that has no
    approved version; and, when the set names no data dictionary, a warning for a project with
    tabular data, or whose inventory is not known, that has none approved."""
    approved = set(kinds)
    repository = requirements["repository_name"]
    checks: tuple[tuple[Severity, str, str], ...] = (
        (VIOLATION, "required_documents", "requires"),
        (WARNING, "recommended_documents", "recommends"),
    )
    named: set[str] = set()
    for severity, key, verb in checks:
        for kind in requirements.get(key, []):
            named.add(kind)
            if kind not in approved:
                yield _document(
                    severity,
                    f"{repository} {verb} a {kind_name(kind)}, and none has been approved.",
                    project_id,
                    kind,
                )
    dictionary = DocumentKind.DATA_DICTIONARY.value
    if dictionary not in named | approved and (inventory is None or _tabular(inventory)):
        yield _document(
            WARNING,
            "No data dictionary has been approved. A dictionary that says what each column of "
            f"the data's tables means helps others reuse them, though {repository} does not ask "
            "for one.",
            project_id,
            dictionary,
        )


def filled_by_repository(project_id: str, requirements: Mapping[str, Any]) -> Iterator[Result]:
    """What the repository fills in itself, as information: the researcher is not asked for it."""
    filled = requirements.get("filled_by_repository") or []
    if not filled:
        return
    names = [_words(prop) for prop in filled]
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    yield Result(
        INFO,
        f"{requirements['repository_name']} fills in the {listed} when it registers the record, "
        "so you need not supply them.",
        project_iri(project_id),
        FILLED_CHECK,
    )


def located(results: Iterable[Result], requirements: Mapping[str, Any]) -> Iterator[Result]:
    """`results` about the record's fields, each with its field's label and the page where its
    value is supplied, found by the schema.org term the result's path names."""
    fields = {
        f"http://schema.org/{field['schema_org']}": field
        for field in requirements.get("fields", [])
    }
    for result in results:
        field = fields.get(result.path or "")
        if field is None:
            yield result
        else:
            yield replace(
                result,
                field=field.get("form_label") or field["property"],
                supplied_on=field.get("supplied_on") or DOCUMENTS,
            )


def kind_name(kind: str) -> str:
    return {
        DocumentKind.METADATA_RECORD.value: "metadata record",
        DocumentKind.README.value: "README",
        DocumentKind.DATA_DICTIONARY.value: "data dictionary",
        DocumentKind.DMP.value: "data management plan",
    }.get(kind, kind.replace("_", " "))


def _document(severity: Severity, message: str, project_id: str, kind: str) -> Result:
    return Result(
        severity,
        message,
        project_iri(project_id),
        DOCUMENT_CHECK,
        field=kind_name(kind),
        supplied_on=DOCUMENTS,
    )


def _tabular(inventory: Mapping[str, Any]) -> bool:
    return any(
        entry.get("file_fields") or entry.get("file_media_type") in TABULAR
        for entry in inventory.get("inventory_files") or []
    )


def _words(prop: str) -> str:
    """A DataCite property in words: publicationYear as publication year."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prop).lower()
