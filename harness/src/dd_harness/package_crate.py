"""The RO-Crate parts of a deposit package (docs/specs/deposit.md): the files `dd_harness.deposit`
writes into the crate, the people and runs it names, each data file it describes without holding,
and the zip the crate is written to."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from rocrate.model import ContextEntity, DataEntity, Person
from rocrate.rocrate import ROCrate

from dd_harness.disclosure import version_id
from dd_harness.provenance import AGENT_BASE, VALIDATION_FILE
from dd_harness.shacl import DD
from dd_harness.storage import RunStorage

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
# A fixed time for every zip entry, so a package's bytes depend on its content alone.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass
class CrateFiles:
    """The files written into a crate from a working folder, and the people it names, each
    added once."""

    crate: ROCrate
    work: Path
    people: dict[str, Any] = field(default_factory=dict)

    def put(self, name: str, content: bytes, media_type: str, title: str, about: str) -> Any:
        """Add `content` to the crate as the file `name`, with its size and SHA-256."""
        source = self.work / name.replace("/", "__")
        source.write_bytes(content)
        return self.crate.add_file(
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

    def person(self, principal: Mapping[str, Any]) -> Any:
        """The crate's entity for `principal`, added the first time it is named."""
        key = principal["principal_id"]
        if key not in self.people:
            self.people[key] = self.crate.add(
                Person(self.crate, key, properties={"name": principal["name"]})
            )
        return self.people[key]


def add_approval(
    files: CrateFiles,
    document: Mapping[str, Any],
    version: Mapping[str, Any],
    entity: Any,
    kind_name: str,
) -> None:
    """The decision that approved `version` of `document`, whose file is `entity`: who made it,
    when, and why, where they said."""
    crate = files.crate
    decision = version["decision"]
    approval = crate.add(
        ContextEntity(
            crate,
            f"#approval-{document['document_id']}-v{version['version']}",
            properties={
                "@type": "AssessAction",
                "name": f"Approval of {kind_name} version {version['version']}",
                "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
                "endTime": decision["decided_at"],
                **({"description": decision["reason"]} if decision.get("reason") else {}),
            },
        )
    )
    approval["agent"] = files.person(decision["decided_by"])
    approval["object"] = entity


def produced_action(
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
    results = [r for r in as_list(action.get("result")) if r is not None]
    action["result"] = [*results, made] if results else made


def add_run(crate: ROCrate, runs: RunStorage, invocation_id: str) -> dict[str, bytes]:
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
                "conformsTo": creative_work(crate, RO_CRATE, "RO-Crate"),
                "subjectOf": descriptor,
            },
        )
    )
    if action is not None:
        action["subjectOf"] = dataset
    return files


def add_data_file(crate: ROCrate, entry: Mapping[str, Any]) -> None:
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


def creative_work(crate: ROCrate, iri: str, name: str) -> Any:
    """A specification, licence or vocabulary an entity conforms to, named in the crate."""
    found = crate.get(iri)
    if found is None:
        found = crate.add(
            ContextEntity(crate, iri, properties={"@type": "CreativeWork", "name": name})
        )
    return found


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def json_bytes(document: Any) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")


def zip_folder(folder: Path) -> bytes:
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
