"""Validation of a project against its chosen repository's requirements, and the deposit package
built from a valid one (docs/specs/deposit.md).

`validate` reads the project log and writes nothing. It checks the project against the merged
requirement set recorded for the repository chosen last:

- that every document kind the set requires has an approved version, and, as warnings, every
  kind it recommends;
- that the approved metadata record, read as RDF through the set's own DataCite to schema.org
  field table, has every required field and, as warnings, every recommended one. These checks are
  SHACL shapes generated from the fields and run by pySHACL;
- that the record's licence is one the set lists, when it lists any;
- that every inventory entry has an accepted media type and is within the size limits, and the
  inventory as a whole within the item size, when the set states them.

Every result, whichever check made it, is written in the W3C SHACL Validation Report vocabulary,
as one report (docs/specs/contract.md). The project is valid when the report has no
`sh:Violation`; warnings, including those from resolving the repository choice, do not block.

`check` validates and keeps the report in the project log. `build_package` does the same, and,
only from a valid report, writes the package: one zip whose root `ro-crate-metadata.json`
describes the dataset. It holds each document's latest approved version, the inventory, the merged
set, the validation report, the project log, the disclosure of generative AI and the Process Run
Crate of each run behind an approved version. It holds no data file: each is described, with its
path, size and SHA-256, and marked as not included.

pySHACL runs, and every result is written, through `dd_harness.shacl`
(docs/specs/dependencies.md).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

from rdflib import BNode, Graph, Namespace, URIRef
from rdflib import Literal as RdfLiteral
from rdflib.namespace import RDF
from rocrate.model import ContextEntity, DataEntity, Person
from rocrate.rocrate import ROCrate

from dd_harness.disclosure import disclose, ni, version_chain, version_id
from dd_harness.projects import APPROVED, ProjectError
from dd_harness.provenance import AGENT_BASE, VALIDATION_FILE
from dd_harness.shacl import DD, SH, VIOLATION, WARNING, Result, Severity
from dd_harness.shacl import report_jsonld as shacl_report
from dd_harness.shacl import run as run_shacl
from dd_harness.storage import ProjectStorage, RunStorage
from dd_sdk.contract.models import DocumentKind, Principal, now

SCHEMA = Namespace("http://schema.org/")
__all__ = ["VIOLATION", "WARNING", "Result", "Severity"]  # kept here for deposit's callers

# The constraint component a result that pySHACL did not make names: the check that made it.
DOCUMENT_CHECK = DD + "RequiredDocumentConstraintComponent"
RECORD_CHECK = DD + "MetadataRecordConstraintComponent"
LICENCE_CHECK = DD + "LicenceConstraintComponent"
INVENTORY_CHECK = DD + "InventoryConstraintComponent"
MEDIA_TYPE_CHECK = DD + "MediaTypeConstraintComponent"
FILE_SIZE_CHECK = DD + "FileSizeConstraintComponent"
ITEM_SIZE_CHECK = DD + "ItemSizeConstraintComponent"
REPOSITORY_CHECK = DD + "RepositoryChoiceConstraintComponent"

# How each DataCite property holds its value, in DataCite's JSON form: the key of the value in
# each entry of a property whose value is a list of objects. It mirrors advisor.metadata's rule
# table; the harness keeps its own, since it imports no agent (docs/specs/system.md).
VALUE_KEYS: Final = {
    "titles": "title",
    "creators": "name",
    "contributors": "name",
    "subjects": "subject",
    "descriptions": "description",
    "dates": "date",
    "rightsList": "rights",
    "fundingReferences": "funderName",
    "relatedIdentifiers": "relatedIdentifier",
    "geoLocations": "geoLocationPlace",
}

# The files of the package beside its documents and runs (docs/specs/deposit.md).
INVENTORY_NAME = "inventory.json"
REQUIREMENTS_NAME = "requirements.json"
REPORT_NAME = "validation-report.jsonld"
LOG_NAME = "project-log.jsonl"
STATEMENT_NAME = "use-of-generative-ai.md"
PROVENANCE_NAME = "provenance.jsonld"
# The files of a Process Run Crate, as the conductor keeps them (dd_harness.provenance).
CRATE_FILES = (
    "ro-crate-metadata.json",
    "request.json",
    "envelope.json",
    "spans.jsonl",
    VALIDATION_FILE,
)
RO_CRATE = "https://w3id.org/ro/crate"
INCLUDED = "includedInPackage"
INCLUDED_IRI = DD + "included_in_package"
EXTENSIONS = {
    "application/json": "json",
    "application/ld+json": "jsonld",
    "text/markdown": "md",
    "text/plain": "txt",
    "text/csv": "csv",
}
# A fixed time for every zip entry, so a package's bytes depend on its content alone.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class PackageRefusedError(ProjectError):
    """The project is not valid against its repository's requirements, so no package is built.
    The validation, with every violation, is in `validation`; it is kept in the project log."""

    def __init__(self, validation: Validation) -> None:
        reasons = "; ".join(r.message for r in validation.violations)
        super().__init__(f"the project is not valid for deposit: {reasons}")
        self.validation = validation


@dataclass(frozen=True)
class Validation:
    """The validation of a project against the merged requirement set recorded for it."""

    project_id: str
    made_at: datetime
    # The digest of the merged requirement set checked against, or None if none was chosen.
    requirements_digest: str | None
    results: tuple[Result, ...]

    @property
    def conforms(self) -> bool:
        return not self.violations

    @property
    def violations(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.severity == VIOLATION)

    @property
    def warnings(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.severity == WARNING)

    def report_jsonld(self) -> dict[str, Any]:
        """The SHACL Validation Report, in JSON-LD."""
        about: dict[str, Any] = {
            "dd:project": {"@id": _project_iri(self.project_id)},
            "dd:validated_at": {"@value": self.made_at.isoformat(), "@type": "xsd:dateTime"},
        }
        if self.requirements_digest is not None:
            about["dd:requirements"] = {"@id": ni(self.requirements_digest)}
        return shacl_report(self.results, **about)


@dataclass(frozen=True)
class Package:
    """A deposit package, as the project log keeps it."""

    digest: str
    content: bytes
    validation: Validation


def validate(projects: ProjectStorage, project_id: str) -> Validation:
    """The validation of the project against the merged requirement set recorded for the
    repository chosen last. Reads the project log and writes nothing. Raises
    `UnknownProjectError` for an unknown project."""
    made_at = now()
    requirements = projects.requirements(project_id)
    if requirements is None:
        result = Result(
            VIOLATION,
            "No repository has been chosen, so there are no requirements to check the project "
            "against.",
            _project_iri(project_id),
            REPOSITORY_CHECK,
        )
        return Validation(project_id, made_at, None, (result,))
    digest = _requirements_digest(projects, project_id)
    repository = requirements["repository_name"]
    results: list[Result] = [
        Result(WARNING, warning, _project_iri(project_id), REPOSITORY_CHECK)
        for warning in requirements.get("warnings", [])
    ]
    approved = _approved(projects.documents(project_id))
    results += _check_documents(project_id, requirements, approved)
    record = projects.metadata_record(project_id)
    if record is not None:
        results += _check_record(record, requirements)
    inventory = projects.inventory(project_id)
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
    return Validation(project_id, made_at, digest, tuple(results))


def check(
    projects: ProjectStorage, project_id: str, *, acted_for: Principal, caused_by: str
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
    projects: ProjectStorage,
    runs: RunStorage,
    project_id: str,
    *,
    acted_for: Principal,
    caused_by: str,
) -> Package:
    """Validate the project, keep the report, and, if it has no violation, build the deposit
    package and keep it in the project log by its digest.

    Raises `PackageRefusedError`, with the report kept, if the project is not valid, and
    `UnknownProjectError` for an unknown project."""
    validation, report_digest = check(
        projects, project_id, acted_for=acted_for, caused_by=caused_by
    )
    if not validation.conforms:
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


def _check_documents(
    project_id: str,
    requirements: Mapping[str, Any],
    approved: list[tuple[dict[str, Any], dict[str, Any]]],
) -> Iterator[Result]:
    kinds = {document["document_kind"] for document, _ in approved}
    repository = requirements["repository_name"]
    checks: tuple[tuple[Severity, str, str], ...] = (
        (VIOLATION, "required_documents", "requires"),
        (WARNING, "recommended_documents", "recommends"),
    )
    for severity, key, verb in checks:
        for kind in requirements.get(key, []):
            if kind not in kinds:
                yield Result(
                    severity,
                    f"{repository} {verb} a {_kind_name(kind)}, and none has been approved.",
                    _project_iri(project_id),
                    DOCUMENT_CHECK,
                )


def _check_record(record: Mapping[str, Any], requirements: Mapping[str, Any]) -> Iterator[Result]:
    ref = record["version_ref"]
    focus = version_id(ref["document_id"], ref["version"])
    try:
        attributes = datacite_attributes(record["document_text"])
    except ValueError as exc:
        yield Result(
            VIOLATION,
            f"The approved metadata record is not a DataCite record in JSON: {exc}.",
            focus,
            RECORD_CHECK,
        )
        return
    yield from _check_fields(focus, attributes, requirements)
    yield from _check_licence(focus, attributes, requirements)


def datacite_attributes(text: str) -> dict[str, Any]:
    """The attributes of a DataCite record in its JSON form, as `advisor.metadata` writes it or
    as the DataCite REST API returns it (`{"data": {"attributes": ...}}`). Raises `ValueError` if
    the text is not one."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"it is not JSON ({exc.msg} at line {exc.lineno})") from None
    if not isinstance(document, dict):
        raise ValueError("it is not a JSON object")
    data = document.get("data")
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        attributes: dict[str, Any] = data["attributes"]
        return attributes
    return document


def field_values(attributes: Mapping[str, Any], field: Mapping[str, Any]) -> list[str]:
    """The values of one requirement field in a DataCite record: each entry of the property that
    matches the field's qualifier, as text. An absent, empty or null value is no value."""
    head, _, rest = field["property"].partition(".")
    value = attributes.get(head)
    if rest:
        value = value.get(rest) if isinstance(value, dict) else None
        entries = [value]
    else:
        entries = value if isinstance(value, list) else [value]
    qualifier = field.get("qualifier") or {}
    found = []
    for entry in entries:
        if isinstance(entry, dict):
            if any(entry.get(key) != wanted for key, wanted in qualifier.items()):
                continue
            entry = entry.get(VALUE_KEYS.get(head, ""))
        elif qualifier:
            continue
        if isinstance(entry, str | int | float) and str(entry).strip():
            found.append(str(entry).strip())
    return found


def _check_fields(
    focus: str, attributes: Mapping[str, Any], requirements: Mapping[str, Any]
) -> Iterator[Result]:
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
        term = SCHEMA[field["schema_org"]]
        for value in field_values(attributes, field):
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
    order = [SCHEMA[f["schema_org"]] for f in requirements.get("fields", [])]
    yield from sorted(
        found, key=lambda r: (r.severity != VIOLATION, order.index(URIRef(r.path or "")))
    )


def _check_licence(
    focus: str, attributes: Mapping[str, Any], requirements: Mapping[str, Any]
) -> Iterator[Result]:
    accepted = requirements.get("licences")
    rights = [r for r in attributes.get("rightsList") or [] if isinstance(r, dict)]
    if not accepted or not rights:
        return
    wanted = {_licence_key(licence) for licence in accepted}
    for entry in rights:
        names = {
            _licence_key(str(entry[key]))
            for key in ("rightsIdentifier", "rightsUri", "rights")
            if entry.get(key)
        }
        if names & wanted:
            return
    named = ", ".join(
        str(entry.get("rightsIdentifier") or entry.get("rightsUri") or entry.get("rights"))
        for entry in rights
    )
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


def _requirements_digest(projects: ProjectStorage, project_id: str) -> str | None:
    chosen = [e for e in projects.events(project_id) if e["event"] == "repository_chosen"]
    return str(chosen[-1]["digest"]) if chosen else None


def _field_name(field: Mapping[str, Any]) -> str:
    """How a message names a field: its form label, if the repository gives one, and the DataCite
    property it is."""
    qualifier = ", ".join(f"{k} {v}" for k, v in (field.get("qualifier") or {}).items())
    datacite = f"{field['property']}{f', {qualifier}' if qualifier else ''}"
    label = field.get("form_label")
    return f"{label} ({datacite})" if label else datacite


def _kind_name(kind: str) -> str:
    return {
        DocumentKind.METADATA_RECORD.value: "metadata record",
        DocumentKind.README.value: "README",
        DocumentKind.DATA_DICTIONARY.value: "data dictionary",
        DocumentKind.DMP.value: "data management plan",
    }.get(kind, kind.replace("_", " "))


def _project_iri(project_id: str) -> str:
    return f"urn:uuid:{project_id}"


def _file_iri(project_id: str, path: str) -> str:
    return f"urn:uuid:{project_id}#file/{quote(path)}"


# --- The package ---------------------------------------------------------------------------------


def _package(
    projects: ProjectStorage, runs: RunStorage, project_id: str, validation: Validation
) -> tuple[bytes, dict[str, Any]]:
    """The package's bytes, and what the project log says of it."""
    requirements = projects.requirements(project_id) or {}
    inventory = projects.inventory(project_id) or {}
    record = projects.metadata_record(project_id) or {}
    approved = _approved(projects.documents(project_id))
    disclosure = disclose(projects, runs, project_id)
    with tempfile.TemporaryDirectory(prefix="dd-package-") as tmp:
        work, out = Path(tmp) / "work", Path(tmp) / "crate"
        work.mkdir()
        crate = ROCrate()
        crate.metadata.extra_terms[INCLUDED] = INCLUDED_IRI
        root = crate.root_dataset
        _describe_root(crate, record, validation.made_at)

        def put(name: str, content: bytes, media_type: str, title: str, about: str) -> Any:
            source = work / name.replace("/", "__")
            source.write_bytes(content)
            return crate.add_file(
                source,
                dest_path=name,
                properties={
                    "name": title,
                    "description": about,
                    "encodingFormat": media_type,
                    "contentSize": str(len(content)),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
            )

        people: dict[str, Any] = {}

        def person(principal: Mapping[str, Any]) -> Any:
            key = principal["principal_id"]
            if key not in people:
                people[key] = crate.add(Person(crate, key, properties={"name": principal["name"]}))
            return people[key]

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
                version.get("document_title") or _kind_name(kind).capitalize(),
                f"The approved {_kind_name(kind)}, version {version['version']}.",
            )
            entity["identifier"] = version_id(document["document_id"], version["version"])
            entity["version"] = str(version["version"])
            if version.get("conforms_to"):
                entity["conformsTo"] = _creative_work(
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
                _produced(crate, made, document, link, person)
            decision = version["decision"]
            approval = crate.add(
                ContextEntity(
                    crate,
                    f"#approval-{document['document_id']}-v{version['version']}",
                    properties={
                        "@type": "AssessAction",
                        "name": f"Approval of {_kind_name(kind)} version {version['version']}",
                        "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
                        "endTime": decision["decided_at"],
                        **({"description": decision["reason"]} if decision.get("reason") else {}),
                    },
                )
            )
            approval["agent"] = person(decision["decided_by"])
            approval["object"] = entity
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
            attached |= _add_run(crate, runs, invocation_id)

        put(
            INVENTORY_NAME,
            _json(inventory),
            "application/json",
            "Inventory of the data files",
            "The FileInventory the data files are described from (docs/specs/projects.md).",
        )
        put(
            REQUIREMENTS_NAME,
            _json(requirements),
            "application/json",
            f"Requirements of {requirements.get('repository_name', 'the repository')}",
            "The merged requirement set the project was validated against, naming each set "
            "used by its version and SHA-256.",
        )
        put(
            REPORT_NAME,
            _json(validation.report_jsonld()),
            "application/ld+json",
            "Validation report",
            "The SHACL Validation Report of the project against its repository's requirements.",
        )["conformsTo"] = _creative_work(crate, str(SH), "Shapes Constraint Language (SHACL)")
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
            _json(disclosure.prov_jsonld()),
            "application/ld+json",
            "Provenance of the approved documents",
            "The PROV-O graph of each approved version and how it came about.",
        )["conformsTo"] = _creative_work(crate, "http://www.w3.org/ns/prov#", "PROV-O")

        for entry in inventory.get("inventory_files") or []:
            _add_data_file(crate, entry)

        root["mentions"] = [e for e in crate.contextual_entities if e.type == "AssessAction"]
        crate.write(out)
        for name, data in attached.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(data)
        content = _zip(out)
    about = {
        "requirements_digest": validation.requirements_digest,
        "documents": documents,
        "runs": included_runs,
        "file_count": len(inventory.get("inventory_files") or []),
    }
    return content, about


def _describe_root(crate: ROCrate, record: Mapping[str, Any], made_at: datetime) -> None:
    """The root dataset's properties, from the approved metadata record through the same
    DataCite to schema.org mapping the validation reads."""
    root = crate.root_dataset
    root["datePublished"] = made_at.date().isoformat()
    attributes: Mapping[str, Any] = {}
    if record.get("document_text"):
        try:
            attributes = datacite_attributes(record["document_text"])
        except ValueError:
            attributes = {}

    def values(prop: str, **qualifier: str) -> list[str]:
        return field_values(attributes, {"property": prop, "qualifier": qualifier or None})

    for term, found in (
        ("name", values("titles")),
        ("description", values("descriptions", descriptionType="Abstract")),
        ("keywords", values("subjects")),
        ("dateCreated", values("dates", dateType="Created")),
        ("additionalType", values("types.resourceTypeGeneral")),
    ):
        if found:
            root[term] = ", ".join(found) if term == "keywords" else found[0]
    creators = []
    for n, name in enumerate(values("creators")):
        creators.append(crate.add(Person(crate, f"#creator-{n + 1}", properties={"name": name})))
    if creators:
        root["creator"] = creators if len(creators) > 1 else creators[0]
    licences = [
        str(r.get("rightsUri") or r.get("rightsIdentifier") or r.get("rights"))
        for r in attributes.get("rightsList") or []
        if isinstance(r, dict) and (r.get("rightsUri") or r.get("rightsIdentifier"))
    ]
    if licences:
        licence = licences[0]
        if not licence.startswith(("http://", "https://")):
            licence = f"https://spdx.org/licenses/{licence}"
        root["license"] = _creative_work(crate, licence, licence)


def _produced(
    crate: ROCrate,
    made: Any,
    document: Mapping[str, Any],
    version: Mapping[str, Any],
    person: Any,
) -> None:
    """The action that produced a version, `made`: the run that drafted it, or a person's
    edit."""
    drafted_by = version.get("drafted_by")
    if drafted_by:
        action_id = f"#run-{drafted_by['invocation_id']}"
        agent = crate.add(
            ContextEntity(
                crate,
                AGENT_BASE + drafted_by["agent_id"],
                properties={
                    "@type": "SoftwareApplication",
                    "name": drafted_by["agent_id"],
                    "url": AGENT_BASE + drafted_by["agent_id"],
                    "version": drafted_by["agent_version"],
                },
            )
        )
        properties = {
            "@type": "CreateAction",
            "name": f"Run {drafted_by['invocation_id']}",
            "identifier": drafted_by["invocation_id"],
        }
        action = crate.get(action_id) or crate.add(ContextEntity(crate, action_id, properties))
        action["instrument"] = agent
        action["agent"] = person(version["added_by"])
    else:
        action_id = f"#edit-{document['document_id']}-v{version['version']}"
        action = crate.add(
            ContextEntity(
                crate,
                action_id,
                properties={
                    "@type": "CreateAction",
                    "name": f"Edit making version {version['version']}",
                    "endTime": version["added_at"],
                },
            )
        )
        action["agent"] = person(version["added_by"])
        revises = version.get("revises")
        if revises:
            action["object"] = {"@id": version_id(revises["document_id"], revises["version"])}
    results = [r for r in _as_list(action.get("result")) if r is not None]
    action["result"] = [*results, made] if results else made


def _add_run(crate: ROCrate, runs: RunStorage, invocation_id: str) -> dict[str, bytes]:
    """The Process Run Crate of a run behind an approved version, as an attached crate. Returns
    its files, each by its path in the package, to be written beside the crate."""
    files = {
        f"runs/{invocation_id}/{name}": data
        for name in CRATE_FILES
        if (data := runs.get_artifact(invocation_id, f"crate/{name}")) is not None
    }
    action = crate.get(f"#run-{invocation_id}")
    if f"runs/{invocation_id}/ro-crate-metadata.json" not in files:
        # The run kept no crate (DD_WRITE_CRATE=0): it is named, and nothing is made up for it.
        if action is not None:
            action["description"] = "This run kept no Process Run Crate."
        return {}
    descriptor = crate.add(
        DataEntity(
            crate,
            f"runs/{invocation_id}/ro-crate-metadata.json",
            properties={
                "@type": "File",
                "name": f"RO-Crate metadata of run {invocation_id}",
                "encodingFormat": "application/ld+json",
                "contentSize": str(len(files[f"runs/{invocation_id}/ro-crate-metadata.json"])),
            },
        )
    )
    dataset = crate.add(
        DataEntity(
            crate,
            f"runs/{invocation_id}/",
            properties={
                "@type": "Dataset",
                "name": f"Process Run Crate of run {invocation_id}",
                "description": "The record of the run, written by the harness after it ended.",
                "conformsTo": _creative_work(crate, RO_CRATE, "RO-Crate"),
                "subjectOf": descriptor,
            },
        )
    )
    if action is not None:
        action["subjectOf"] = dataset
    return files


def _add_data_file(crate: ROCrate, entry: Mapping[str, Any]) -> None:
    """A data file the inventory describes, marked as not in the package: the researcher adds it
    at deposit, and its digest shows it is the file described."""
    properties: dict[str, Any] = {
        "@type": "File",
        "name": entry["file_path"],
        "contentSize": str(entry["file_size"]),
        "sha256": entry["file_sha256"],
        "localPath": entry["file_path"],
        INCLUDED: False,
        "description": "Not in the package: the researcher adds this file at deposit.",
    }
    if entry.get("file_media_type"):
        properties["encodingFormat"] = entry["file_media_type"]
    crate.add(DataEntity(crate, f"#file/{quote(entry['file_path'])}", properties=properties))


def _creative_work(crate: ROCrate, iri: str, name: str) -> Any:
    """A specification, licence or vocabulary an entity conforms to, named in the crate."""
    found = crate.get(iri)
    if found is None:
        found = crate.add(
            ContextEntity(crate, iri, properties={"@type": "CreativeWork", "name": name})
        )
    return found


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _json(document: Any) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _zip(folder: Path) -> bytes:
    """The folder as a zip, with an entry for each folder as well as each file, in path order and
    with a fixed time."""
    with tempfile.SpooledTemporaryFile() as buffer:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                name = path.relative_to(folder).as_posix()
                if path.is_dir():
                    info = zipfile.ZipInfo(name + "/", ZIP_TIME)
                    info.external_attr = (0o40755 << 16) | 0x10
                    archive.writestr(info, b"")
                    continue
                info = zipfile.ZipInfo(name, ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
        buffer.seek(0)
        return buffer.read()
