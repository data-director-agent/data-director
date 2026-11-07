"""SHACL validation and the W3C SHACL Validation Report (docs/specs/contract.md).

Two checks use it. Deposit validation checks a project against shapes generated from its
repository's requirements (dd_harness.deposit). The conductor checks an agent's payload against
the shapes its class carries on the card, `validate_payload`, and keeps the report beside the run.
That check only reports: a payload that breaks its shapes keeps its outcome, since the class's
JSON Schema, which a payload must pass, already decides what is structurally valid.

Every result, whichever check made it, is a `Result`, and a report is written in JSON-LD in the
`sh:` vocabulary; no bespoke report type is defined.

This module is the only importer of `pyshacl` at run time (docs/specs/dependencies.md).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, Final, Literal

from pyshacl import validate as shacl_validate
from rdflib import Graph, Namespace
from rdflib.namespace import RDF, XSD
from rdflib.plugins.parsers.jsonld import to_rdf

from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.rdf import payload_jsonld

SH = Namespace("http://www.w3.org/ns/shacl#")
DD = "https://w3id.org/data-director/"

type Severity = Literal["violation", "warning"]
VIOLATION: Final = "violation"
WARNING: Final = "warning"

# The constraint component of a result that pySHACL did not make because it could not run: the
# payload could not be read as RDF, or the shapes could not be parsed.
UNCHECKED = DD + "PayloadNotCheckedConstraintComponent"
REPORT_CONTEXT: Final = {"sh": str(SH), "dd": DD, "xsd": str(XSD), "schema": "http://schema.org/"}


@dataclass(frozen=True)
class Result:
    """One result of a validation, as an `sh:ValidationResult` says it."""

    severity: Severity
    message: str
    focus: str
    component: str
    path: str | None = None

    def to_jsonld(self) -> dict[str, Any]:
        node: dict[str, Any] = {
            "@type": "sh:ValidationResult",
            "sh:resultSeverity": {"@id": f"sh:{self.severity.capitalize()}"},
            "sh:focusNode": {"@id": self.focus},
            "sh:resultMessage": self.message,
            "sh:sourceConstraintComponent": {"@id": self.component},
        }
        if self.path is not None:
            node["sh:resultPath"] = {"@id": self.path}
        return node


def conforms(results: Iterable[Result]) -> bool:
    """A validation conforms when none of its results is a violation; warnings do not block."""
    return all(r.severity != VIOLATION for r in results)


def report_jsonld(results: Iterable[Result], **about: Any) -> dict[str, Any]:
    """The SHACL Validation Report of `results`, in JSON-LD, with `about` as further properties
    of the report (each key a `dd:` or other prefixed term of `REPORT_CONTEXT`)."""
    found = list(results)
    return {
        "@context": dict(REPORT_CONTEXT),
        "@type": "sh:ValidationReport",
        "sh:conforms": conforms(found),
        "sh:result": [r.to_jsonld() for r in found],
        **about,
    }


def run(data: Graph, shapes: Graph) -> list[Result]:
    """pySHACL's results for `data` against `shapes`, without inference."""
    _, report, _ = shacl_validate(data, shacl_graph=shapes, inference="none", allow_warnings=True)
    assert isinstance(report, Graph)
    found = []
    for node in report.subjects(RDF.type, SH.ValidationResult):
        path = report.value(node, SH.resultPath)
        message = report.value(node, SH.resultMessage)
        found.append(
            Result(
                VIOLATION if report.value(node, SH.resultSeverity) == SH.Violation else WARNING,
                str(message) if message is not None else "",
                str(report.value(node, SH.focusNode)),
                str(report.value(node, SH.sourceConstraintComponent)),
                str(path) if path is not None else None,
            )
        )
    return sorted(found, key=lambda r: (r.severity != VIOLATION, r.path or "", r.message))


@dataclass(frozen=True)
class PayloadValidation:
    """The check of one payload against its class's shapes."""

    invocation_id: str
    schema: ClassSchema
    made_at: datetime
    results: tuple[Result, ...]

    @property
    def conforms(self) -> bool:
        return conforms(self.results)

    def report_jsonld(self) -> dict[str, Any]:
        assert self.schema.shapes is not None
        return report_jsonld(
            self.results,
            **{
                "dd:invocation": {"@id": f"urn:uuid:{self.invocation_id}"},
                "dd:payload_class": self.schema.name,
                "dd:payload_schema": self.schema.digest,
                "dd:shapes": self.schema.shapes.digest,
                "dd:validated_at": {"@value": self.made_at.isoformat(), "@type": "xsd:dateTime"},
            },
        )

    def report_bytes(self) -> bytes:
        return (json.dumps(self.report_jsonld(), indent=2) + "\n").encode("utf-8")


def payload_iri(invocation_id: str) -> str:
    """The IRI the payload of an invocation is read as, so that a report names its focus."""
    return f"urn:uuid:{invocation_id}#payload"


def validate_payload(
    invocation_id: str, payload: Mapping[str, Any], schema: ClassSchema, made_at: datetime
) -> PayloadValidation:
    """`payload` checked against the shapes of its class, `schema`, which must have shapes. A
    payload that cannot be read as RDF, or shapes that cannot be parsed, give one violation
    saying so rather than an exception: the check reports, and never decides the outcome."""
    if schema.shapes is None:
        raise ValueError(f"class {schema.name!r} has no shapes")
    focus = payload_iri(invocation_id)
    try:
        shapes = _shapes(schema.shapes.digest, schema.shapes.shacl)
        document = {"@id": focus, **payload_jsonld(payload, schema)}
        data = Graph()
        # rdflib's JSON-LD reader proper builds a deprecated ConjunctiveGraph; its to_rdf does not.
        to_rdf(document, data)
        results = run(data, shapes)
    except Exception as exc:  # noqa: BLE001 — any failure is reported, never raised into a run
        results = [
            Result(
                VIOLATION,
                f"The payload could not be checked against the shapes of {schema.name}: {exc}",
                focus,
                UNCHECKED,
            )
        ]
    return PayloadValidation(invocation_id, schema, made_at, tuple(results))


@lru_cache(maxsize=64)
def _shapes(digest: str, shacl: str) -> Graph:
    """The parsed shapes, by digest: an agent's classes are checked on every run."""
    del digest  # the cache key; the shapes were checked against it when the card was read
    return Graph().parse(data=shacl, format="turtle")
