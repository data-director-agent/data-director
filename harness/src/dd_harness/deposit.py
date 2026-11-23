"""Validation of a project against its chosen repository's requirements, and the deposit package
built from a valid one (docs/specs/deposit.md).

`validate` reads the project log and writes nothing. It checks the project against the merged
requirement set recorded for the repository chosen last:

- that every document kind the set requires has an approved version, and, as warnings, every
  kind it recommends and a data dictionary for tabular data (`dd_harness.deposit_checks`);
- that the approved metadata record is in a pair of standard and serialisation a registered
  definition covers, and, read with that definition, has every required field and, as warnings,
  every recommended one, each under its field's term. These checks are SHACL shapes generated from
  the fields and run by pySHACL (docs/specs/metadata-standards.md);
- that the record's licence is one the set lists, when it lists any;
- that every inventory entry has an accepted media type and is within the size limits, and the
  inventory as a whole within the item size, when the set states them;
- as warnings, each item a person must decide before packaging, and the checks they must confirm
  (`dd_harness.deposit_review`);
- as information, what the repository fills in itself.

A result about a document or a field names it, and the page of the project where a person
supplies it (`dd_harness.deposit_checks`).

Every result, whichever check made it, is written in the W3C SHACL Validation Report vocabulary,
as one report (docs/specs/contract.md). The project is valid when the report has no
`sh:Violation`; warnings, including those from resolving the repository choice, and information
do not block. It is ready to package when it is valid and nothing waits on a person
(`dd_harness.deposit_report`).

`check` validates and keeps the report in the project log. `build_package` does the same, and,
only from a report ready to package, writes the package: one zip whose root `ro-crate-metadata.json`
describes the dataset. It holds each document's latest approved version, the inventory, the merged
set, the validation report, the project log, the disclosure of generative AI and the Process Run
Crate of each run behind an approved version. It holds no data file: each is described, with its
path, size and SHA-256, and marked as not included.

pySHACL runs, and every result is written, through `dd_harness.shacl`
(docs/specs/dependencies.md).
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from rdflib import BNode, Graph, URIRef
from rdflib import Literal as RdfLiteral
from rdflib.namespace import RDF
from rocrate.rocrate import ROCrate

from dd_harness import deposit_review
from dd_harness.deposit_checks import (
    DOCUMENT_CHECK,
    REPOSITORY_CHECK,
    check_documents,
    filled_by_repository,
    kind_name,
    located,
    no_repository,
    resolver_warnings,
)
from dd_harness.deposit_record import SCHEMA, describe_root, licences
from dd_harness.deposit_report import Package, PackageRefusedError, Validation
from dd_harness.deposit_report import project_iri as _project_iri
from dd_harness.disclosure import disclose, version_chain, version_id
from dd_harness.metadata_standards import UnreadRecordError, read_record, readable
from dd_harness.package_crate import (
    INCLUDED,
    INCLUDED_IRI,
    CrateFiles,
    add_approval,
    add_data_file,
    add_review,
    add_run,
    creative_work,
    json_bytes,
    produced_action,
    zip_folder,
)
from dd_harness.projects import APPROVED
from dd_harness.shacl import DD, INFO, SH, VIOLATION, WARNING, Result, Severity
from dd_harness.shacl import run as run_shacl
from dd_harness.storage import DepositSource, RunStorage
from dd_metadata_records import Record
from dd_sdk.contract.models import Principal, now
from dd_sdk.contract.requirements import expand_term

# Kept here for deposit's callers.
__all__ = [
    "DOCUMENT_CHECK",
    "INFO",
    "REPOSITORY_CHECK",
    "VIOLATION",
    "WARNING",
    "Package",
    "PackageRefusedError",
    "Result",
    "Severity",
    "Validation",
]

# The constraint component a result that pySHACL did not make names: the check that made it.
RECORD_CHECK = DD + "MetadataRecordConstraintComponent"
LICENCE_CHECK = DD + "LicenceConstraintComponent"
INVENTORY_CHECK = DD + "InventoryConstraintComponent"
MEDIA_TYPE_CHECK = DD + "MediaTypeConstraintComponent"
FILE_SIZE_CHECK = DD + "FileSizeConstraintComponent"
ITEM_SIZE_CHECK = DD + "ItemSizeConstraintComponent"

# The files of the package beside its documents and runs (docs/specs/deposit.md).
INVENTORY_NAME = "inventory.json"
REQUIREMENTS_NAME = "requirements.json"
REPORT_NAME = "validation-report.jsonld"
LOG_NAME = "project-log.jsonl"
STATEMENT_NAME = "use-of-generative-ai.md"
PROVENANCE_NAME = "provenance.jsonld"
EXTENSIONS = {
    "application/json": "json",
    "application/ld+json": "jsonld",
    "text/markdown": "md",
    "text/plain": "txt",
    "text/csv": "csv",
}


def validate(projects: DepositSource, project_id: str) -> Validation:
    """The validation of the project against the merged requirement set recorded for the
    repository chosen last. Reads the project log and writes nothing. Raises
    `UnknownProjectError` for an unknown project."""
    made_at = now()
    requirements = projects.requirements(project_id)
    if requirements is None:
        return Validation(project_id, made_at, None, (no_repository(project_id),))
    digest = _requirements_digest(projects, project_id)
    repository = requirements["repository_name"]
    results = list(resolver_warnings(project_id, requirements))
    kinds = [document["document_kind"] for document, _ in _approved(projects.documents(project_id))]
    inventory = projects.inventory(project_id)
    results += check_documents(project_id, requirements, kinds, inventory)
    record = projects.metadata_record(project_id)
    if record is not None:
        results += located(_check_record(record, requirements), requirements)
    results += filled_by_repository(project_id, requirements)
    if inventory is None:
        results.append(
            Result(
                VIOLATION,
                "No inventory of the data files has been added, so the package could not say "
                f"which files to deposit in {repository}.",
                _project_iri(project_id),
                INVENTORY_CHECK,
            )
        )
    else:
        results += _check_inventory(project_id, inventory, requirements)
    review = deposit_review.review(projects, project_id)
    results += review.results(project_id)
    return Validation(project_id, made_at, digest, tuple(results), review)


def check(
    projects: DepositSource, project_id: str, *, acted_for: Principal, caused_by: str
) -> tuple[Validation, str]:
    """Validate the project and keep the report in its log. Returns the validation and the
    report's digest."""
    validation = validate(projects, project_id)
    digest = projects.record_validation(
        project_id,
        validation.report_jsonld(),
        conforms=validation.conforms,
        requirements_digest=validation.requirements_digest,
        acted_for=acted_for,
        caused_by=caused_by,
    )
    return validation, digest


def build_package(
    projects: DepositSource,
    runs: RunStorage,
    project_id: str,
    *,
    acted_for: Principal,
    caused_by: str,
) -> Package:
    """Validate the project, keep the report, and, if it has no violation and nothing waits on
    a person, build the deposit package and keep it in the project log by its digest.

    Raises `PackageRefusedError`, with the report kept, if the project is not ready, and
    `UnknownProjectError` for an unknown project."""
    validation, report_digest = check(
        projects, project_id, acted_for=acted_for, caused_by=caused_by
    )
    if not validation.ready:
        raise PackageRefusedError(validation)
    content, about = _package(projects, runs, project_id, validation)
    digest = projects.record_package(
        project_id,
        content,
        about={"report_digest": report_digest, **about},
        acted_for=acted_for,
        caused_by=caused_by,
    )
    return Package(digest, content, validation)


# --- Validation ----------------------------------------------------------------------------------


def _approved(documents: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Each document with an approved version, and its latest approved version."""
    found = []
    for document in documents:
        approved = [v for v in document["versions"] if v["state"] == APPROVED]
        if approved:
            found.append((document, approved[-1]))
    return found


def _check_record(record: Mapping[str, Any], requirements: Mapping[str, Any]) -> Iterator[Result]:
    ref = record["version_ref"]
    focus = version_id(ref["document_id"], ref["version"])
    try:
        read = read_record(record)
    except UnreadRecordError as exc:
        yield Result(VIOLATION, f"The approved metadata record {exc}.", focus, RECORD_CHECK)
        return
    yield from _check_fields(focus, read, requirements)
    yield from _check_licence(focus, read, requirements)


def _check_fields(focus: str, record: Record, requirements: Mapping[str, Any]) -> Iterator[Result]:
    """The record's fields against SHACL shapes generated from the merged set, run by pySHACL."""
    subject = URIRef(focus)
    data = Graph()
    data.add((subject, RDF.type, SCHEMA.Dataset))
    shapes = Graph()
    shape = URIRef(DD + "shapes/DepositRecord")
    shapes.add((shape, RDF.type, SH.NodeShape))
    shapes.add((shape, SH.targetClass, SCHEMA.Dataset))
    repository = requirements["repository_name"]
    for field in requirements.get("fields", []):
        term = URIRef(expand_term(field["term"]))
        for value in record.values(field["property"], field.get("qualifier")):
            data.add((subject, term, RdfLiteral(value)))
        required = field["obligation"] == "required"
        prop = BNode()
        shapes.add((shape, SH.property, prop))
        shapes.add((prop, SH.path, term))
        shapes.add((prop, SH.minCount, RdfLiteral(1)))
        shapes.add((prop, SH.severity, SH.Violation if required else SH.Warning))
        verb = "requires" if required else "recommends"
        shapes.add(
            (
                prop,
                SH.message,
                RdfLiteral(
                    f"The metadata record has no {_field_name(field)}, which {repository} {verb}."
                ),
            )
        )
    found = run_shacl(data, shapes)
    order = [URIRef(expand_term(f["term"])) for f in requirements.get("fields", [])]
    yield from sorted(
        found, key=lambda r: (r.severity != VIOLATION, order.index(URIRef(r.path or "")))
    )


def _check_licence(focus: str, record: Record, requirements: Mapping[str, Any]) -> Iterator[Result]:
    accepted = requirements.get("licences")
    given = licences(record)
    if not accepted or not given:
        return
    wanted = {_licence_key(licence) for licence in accepted}
    for entry in given:
        if {_licence_key(name) for name in entry if name} & wanted:
            return
    named = ", ".join(str(next((name for name in entry if name), None)) for entry in given)
    yield Result(
        VIOLATION,
        f"The metadata record's licence ({named}) is not one {requirements['repository_name']} "
        f"accepts: {', '.join(accepted)}.",
        focus,
        LICENCE_CHECK,
        str(SCHEMA.license),
    )


def _licence_key(licence: str) -> str:
    """A licence as compared: an SPDX identifier, from its identifier or its spdx.org URL, in
    lower case; any other URL as written."""
    for prefix in ("https://spdx.org/licenses/", "http://spdx.org/licenses/"):
        if licence.startswith(prefix):
            licence = licence.removeprefix(prefix).removesuffix(".html")
    return licence.strip().lower()


def _check_inventory(
    project_id: str, inventory: Mapping[str, Any], requirements: Mapping[str, Any]
) -> Iterator[Result]:
    repository = requirements["repository_name"]
    media_types = requirements.get("media_types") or []
    max_file = requirements.get("max_file_size")
    files = inventory.get("inventory_files") or []
    for entry in files:
        path, focus = entry["file_path"], _file_iri(project_id, entry["file_path"])
        if media_types and entry.get("file_media_type") not in media_types:
            kind = entry.get("file_media_type") or "of no identified media type"
            yield Result(
                VIOLATION,
                f"{path} is {kind}, which {repository} does not accept.",
                focus,
                MEDIA_TYPE_CHECK,
            )
        if max_file is not None and entry["file_size"] > max_file:
            yield Result(
                VIOLATION,
                f"{path} is {entry['file_size']} bytes, over the {max_file} bytes {repository} "
                "accepts for one file.",
                focus,
                FILE_SIZE_CHECK,
            )
    max_item = requirements.get("max_item_size")
    total = sum(entry["file_size"] for entry in files)
    if max_item is not None and total > max_item:
        yield Result(
            VIOLATION,
            f"The files come to {total} bytes, over the {max_item} bytes {repository} accepts "
            "for one item.",
            _project_iri(project_id),
            ITEM_SIZE_CHECK,
        )


def _requirements_digest(projects: DepositSource, project_id: str) -> str | None:
    chosen = [e for e in projects.events(project_id) if e["event"] == "repository_chosen"]
    return str(chosen[-1]["digest"]) if chosen else None


def _field_name(field: Mapping[str, Any]) -> str:
    """How a message names a field: its form label, if the repository gives one, and the property
    of the standard it is."""
    qualifier = ", ".join(f"{k} {v}" for k, v in (field.get("qualifier") or {}).items())
    prop = f"{field['property']}{f', {qualifier}' if qualifier else ''}"
    label = field.get("form_label")
    return f"{label} ({prop})" if label else prop


def _file_iri(project_id: str, path: str) -> str:
    return f"urn:uuid:{project_id}#file/{quote(path)}"


# --- The package ---------------------------------------------------------------------------------


def _package(
    projects: DepositSource, runs: RunStorage, project_id: str, validation: Validation
) -> tuple[bytes, dict[str, Any]]:
    """The package's bytes, and what the project log says of it."""
    requirements = projects.requirements(project_id) or {}
    inventory = projects.inventory(project_id) or {}
    record = readable(projects.metadata_record(project_id))
    approved = _approved(projects.documents(project_id))
    disclosure = disclose(projects, runs, project_id)
    with tempfile.TemporaryDirectory(prefix="dd-package-") as tmp:
        work, out = Path(tmp) / "work", Path(tmp) / "crate"
        work.mkdir()
        crate = ROCrate()
        crate.metadata.extra_terms[INCLUDED] = INCLUDED_IRI
        root = crate.root_dataset
        describe_root(crate, record, requirements, validation.made_at)
        files = CrateFiles(crate, work)
        put, person = files.put, files.person

        included_runs: list[str] = []
        documents = []
        for document, version in approved:
            kind = document["document_kind"]
            extension = EXTENSIONS.get(version["media_type"], "txt")
            name = f"documents/{kind}-{document['document_id']}-v{version['version']}.{extension}"
            text = next(
                v["text"] for v in document["versions"] if v["version"] == version["version"]
            )
            entity = put(
                name,
                text.encode("utf-8"),
                version["media_type"],
                version.get("document_title") or kind_name(kind).capitalize(),
                f"The approved {kind_name(kind)}, version {version['version']}.",
            )
            entity["identifier"] = version_id(document["document_id"], version["version"])
            entity["version"] = str(version["version"])
            if version.get("conforms_to"):
                entity["conformsTo"] = creative_work(
                    crate, version["conforms_to"], version["conforms_to"]
                )
            # Each version the approved one came from: the run that drafted it or the person who
            # edited it. The approved version is the file; an earlier one is named by its id.
            for link in version_chain(document, version):
                drafted_by = link.get("drafted_by")
                if drafted_by and drafted_by["invocation_id"] not in included_runs:
                    included_runs.append(drafted_by["invocation_id"])
                made = (
                    entity
                    if link is version
                    else {"@id": version_id(document["document_id"], link["version"])}
                )
                produced_action(crate, made, document, link, person)
            add_approval(files, document, version, entity, kind_name(kind))
            documents.append(
                {
                    "document_id": document["document_id"],
                    "document_kind": kind,
                    "version": version["version"],
                    "digest": version["digest"],
                }
            )

        attached: dict[str, bytes] = {}
        for invocation_id in included_runs:
            attached |= add_run(crate, runs, invocation_id)

        put(
            INVENTORY_NAME,
            json_bytes(inventory),
            "application/json",
            "Inventory of the data files",
            "The FileInventory the data files are described from (docs/specs/projects.md).",
        )
        put(
            REQUIREMENTS_NAME,
            json_bytes(requirements),
            "application/json",
            f"Requirements of {requirements.get('repository_name', 'the repository')}",
            "The merged requirement set the project was validated against, naming each set "
            "used by its version and SHA-256.",
        )
        put(
            REPORT_NAME,
            json_bytes(validation.report_jsonld()),
            "application/ld+json",
            "Validation report",
            "The SHACL Validation Report of the project against its repository's requirements.",
        )["conformsTo"] = creative_work(crate, str(SH), "Shapes Constraint Language (SHACL)")
        put(
            LOG_NAME,
            "".join(
                json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n"
                for e in projects.events(project_id)
            ).encode("utf-8"),
            "application/jsonl",
            "Project log",
            "The project's audit trail: every inventory, repository choice, proposed version, "
            "decision and validation, in order.",
        )
        put(
            STATEMENT_NAME,
            disclosure.statement().encode("utf-8"),
            "text/markdown",
            "Use of generative AI",
            "How each approved document came about, for a person to read and cite.",
        )
        put(
            PROVENANCE_NAME,
            json_bytes(disclosure.prov_jsonld()),
            "application/ld+json",
            "Provenance of the approved documents",
            "The PROV-O graph of each approved version and how it came about.",
        )["conformsTo"] = creative_work(crate, "http://www.w3.org/ns/prov#", "PROV-O")

        for entry in inventory.get("inventory_files") or []:
            add_data_file(crate, entry)
        review = validation.review.to_document() if validation.review else {"items": []}
        add_review(files, review)

        root["mentions"] = [e for e in crate.contextual_entities if e.type == "AssessAction"]
        crate.write(out)
        for name, data in attached.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(data)
        content = zip_folder(out)
    about = {
        "requirements_digest": validation.requirements_digest,
        "documents": documents,
        "runs": included_runs,
        "file_count": len(inventory.get("inventory_files") or []),
        "decided_items": [i["item_id"] for i in review["items"] if i.get("decision")],
    }
    return content, about
