"""Input and payload classes, carried as JSON Schema pinned by digest (docs/specs/contract.md).

An agent owns its input and payload classes. It declares each in its own LinkML file,
`dd-gen-schema` generates a self-contained JSON Schema for it into the agent's package, and the
agent writes a Pydantic model for it. `ClassSchema.of(model)` reads the generated schema of a
model from the package that defines it and refuses a model whose fields differ from the schema's
properties, so the two cannot drift silently.

The agent's card carries every class schema with its digest. The harness rebuilds each one with
`ClassSchema.from_description`, which refuses a schema that does not match its digest, and
validates inputs and payloads against it.

`dd-gen-schema` also writes the class's SHACL shapes and the JSON-LD context that reads its
documents as RDF. Where they are present, the card carries them too, as `shapes`, with a digest
of their own; the harness checks a payload against them and keeps the SHACL Validation Report
with the run. They are optional: a class without them is still governed, and its payloads get
no report. The harness holds no model: what it reads it holds
as an `OpenInput` or an `OpenPayload`, and the class schema, not a Python type, decides what is
valid.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property
from importlib.resources import files
from typing import Any, get_args

from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError

from dd_sdk.contract.models import Frozen, Grounded, OpenInput, OpenPayload
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

# Where `dd-gen-schema` writes a package's class schemas (dd_sdk.schema.gen).
GENERATED = ("schema", "generated")
DESIGNATOR = "schema_class"
GROUNDED_SLOT = "grounded_on"


@dataclass(frozen=True)
class Shapes:
    """A class's SHACL shapes (Turtle) and the JSON-LD context that reads its documents as RDF,
    with the digest of both."""

    shacl: str = field(compare=False)  # the digest stands for them
    context: Mapping[str, Any] = field(compare=False)
    digest: str

    @classmethod
    def of(cls, shacl: str, context: Mapping[str, Any]) -> Shapes:
        return cls(shacl, context, shapes_digest(shacl, context))

    def describe(self) -> dict[str, Any]:
        return {"digest": self.digest, "shacl": self.shacl, "context": dict(self.context)}


class ClassSchemaError(Exception):
    """A class schema is missing, malformed, or disagrees with its model or its digest."""


def schema_digest(json_schema: Mapping[str, Any]) -> str:
    """The sha256 of a class schema, canonicalised as `dd-json-document-v1`."""
    return content_hash(dict(json_schema), DOCUMENT_CANONICALISATION)


def shapes_digest(shacl: str, context: Mapping[str, Any]) -> str:
    """The sha256 of a class's shapes and context, canonicalised as `dd-json-document-v1`."""
    return content_hash({"shacl": shacl, "context": dict(context)}, DOCUMENT_CANONICALISATION)


@dataclass(frozen=True)
class ClassSchema:
    """One input or payload class: its name, its JSON Schema and that schema's digest.

    `model` is the agent's own Pydantic model for the class. It is set on the agent's side only;
    a class schema the harness rebuilt from a card has none.
    """

    name: str
    json_schema: Mapping[str, Any] = field(compare=False)  # the digest stands for it
    digest: str
    model: type[Frozen] | None = field(default=None, compare=False)
    shapes: Shapes | None = field(default=None, compare=False)

    @classmethod
    def of(cls, model: type[Frozen]) -> ClassSchema:
        """The generated schema of `model`, from `schema/generated/` of the package defining it."""
        name = _designated_name(model)
        package = model.__module__.split(".")[0]
        resource = files(package).joinpath(*GENERATED, f"{name}.schema.json")
        try:
            json_schema: dict[str, Any] = json.loads(resource.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError) as exc:
            raise ClassSchemaError(
                f"{package}: no generated schema for {name} ({exc}); run `uv run dd-gen-schema` "
                "on the package's LinkML file"
            ) from exc
        fields, properties = set(model.model_fields), set(json_schema.get("properties", {}))
        if fields != properties:
            raise ClassSchemaError(
                f"{model.__module__}.{model.__name__} and its schema disagree: fields only in the "
                f"model {sorted(fields - properties)}, only in the schema "
                f"{sorted(properties - fields)}"
            )
        found = cls(name, json_schema, schema_digest(json_schema), model, _shapes(package, name))
        found.check()
        return found

    @classmethod
    def from_description(cls, name: str, entry: Mapping[str, Any]) -> ClassSchema:
        """Rebuild a class schema from a card's `schemas` entry. Raises `ClassSchemaError` if the
        schema does not match its digest or does not designate `name`."""
        json_schema = entry.get("json_schema")
        digest = entry.get("digest")
        if not isinstance(json_schema, Mapping) or not isinstance(digest, str):
            raise ClassSchemaError(f"class {name!r}: a schema entry needs json_schema and digest")
        if schema_digest(json_schema) != digest:
            raise ClassSchemaError(f"class {name!r}: the schema does not match its digest")
        found = cls(
            name=name, json_schema=json_schema, digest=digest, shapes=_described_shapes(name, entry)
        )
        found.check()
        return found

    def check(self) -> None:
        """A class schema is valid JSON Schema and designates its own name in `schema_class`."""
        try:
            Draft7Validator.check_schema(dict(self.json_schema))
        except SchemaError as exc:
            raise ClassSchemaError(f"class {self.name!r}: not a valid JSON Schema: {exc}") from exc
        designator = self.json_schema.get("properties", {}).get(DESIGNATOR, {})
        if designator.get("enum") != [self.name] or DESIGNATOR not in self.required:
            raise ClassSchemaError(
                f"class {self.name!r}: the schema does not require {DESIGNATOR} = {self.name!r}"
            )

    @property
    def required(self) -> frozenset[str]:
        return frozenset(self.json_schema.get("required", ()))

    @property
    def grounded(self) -> bool:
        """Whether the class mixes in `Grounded`, as every payload class must
        (docs/specs/contract.md)."""
        return GROUNDED_SLOT in self.required

    def describe(self) -> dict[str, Any]:
        """The class's entry in a card's `schemas`."""
        entry = {"digest": self.digest, "json_schema": dict(self.json_schema)}
        if self.shapes is not None:
            entry["shapes"] = self.shapes.describe()
        return entry

    @cached_property
    def _validator(self) -> Draft7Validator:
        return Draft7Validator(dict(self.json_schema))

    def errors(self, document: Mapping[str, Any]) -> list[str]:
        """Every way `document` fails this class's schema; empty if it conforms."""
        found = sorted(self._validator.iter_errors(dict(document)), key=str)
        return [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in found
        ]

    def parse_input(self, document: Mapping[str, Any]) -> Frozen:
        """The input as the agent's model, or as an `OpenInput` where there is no model."""
        if self.model is not None:
            return self.model.model_validate(dict(document))
        return OpenInput.model_validate(dict(document))

    def parse_payload(self, document: Mapping[str, Any]) -> Grounded:
        """The payload as the agent's model, or as an `OpenPayload` where there is no model."""
        if self.model is not None and issubclass(self.model, Grounded):
            return self.model.model_validate(dict(document))
        return OpenPayload.model_validate(dict(document))


def _designated_name(model: type[Frozen]) -> str:
    info = model.model_fields.get(DESIGNATOR)
    values = get_args(info.annotation) if info is not None else ()
    if len(values) != 1 or not isinstance(values[0], str):
        raise ClassSchemaError(
            f"{model.__name__} has no {DESIGNATOR}: Literal[...] designator with one value"
        )
    return values[0]


def _shapes(package: str, name: str) -> Shapes | None:
    """The class's generated shapes and context, or None where the package has none."""
    generated = files(package).joinpath(*GENERATED)
    shacl, context = (
        generated.joinpath(f"{name}.shacl.ttl"),
        generated.joinpath(f"{name}.context.jsonld"),
    )
    if not shacl.is_file() and not context.is_file():
        return None
    try:
        return Shapes.of(
            shacl.read_text(encoding="utf-8"),
            json.loads(context.read_text(encoding="utf-8")),
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ClassSchemaError(
            f"{package}: the shapes of {name} are incomplete ({exc}); run `uv run dd-gen-schema` "
            "on the package's LinkML file"
        ) from exc


def _described_shapes(name: str, entry: Mapping[str, Any]) -> Shapes | None:
    """A card entry's `shapes`, checked against its digest; None where the entry has none."""
    described = entry.get("shapes")
    if described is None:
        return None
    if not isinstance(described, Mapping):
        raise ClassSchemaError(f"class {name!r}: shapes must be an object")
    shacl, context, digest = (described.get(k) for k in ("shacl", "context", "digest"))
    if not (isinstance(shacl, str) and isinstance(context, Mapping) and isinstance(digest, str)):
        raise ClassSchemaError(f"class {name!r}: shapes need shacl, context and digest")
    if shapes_digest(shacl, context) != digest:
        raise ClassSchemaError(f"class {name!r}: the shapes do not match their digest")
    return Shapes(shacl, context, digest)
