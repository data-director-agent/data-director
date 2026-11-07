"""Generate JSON Schema and SHACL from a LinkML source (docs/specs/contract.md).

`dd-gen-schema` with no argument regenerates the core contract, `data_director.yaml`, into
`generated/` beside it: the envelope and request schemas, the SHACL shapes of the whole core, and
the files of each core class that carries `schema_class`. `dd-gen-schema PATH` does the same for
an agent's own LinkML file, which imports the core as `data_director`: the files of each of its
classes that carries `schema_class`, written to `generated/` beside `PATH`.

Each such class gets three files: its JSON Schema (`<Name>.schema.json`), its SHACL shapes
(`<Name>.shacl.ttl`) and the JSON-LD context that reads its documents as RDF
(`<Name>.context.jsonld`). Each is self-contained: the schema's `$defs`, the shapes and the
context's terms hold only what the class reaches. The JSON Schema's `$comment` names the source
and the command, and the tests compare every generated file against a fresh generation (the
shapes as graphs), so a hand edit fails the suite rather than taking effect.

LinkML is a development dependency (docs/specs/contract.md): it is needed to regenerate a schema,
never to load one.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent
CORE = SCHEMA_DIR / "data_director.yaml"
GENERATED = "generated"
# How an agent's LinkML file names the core in `imports:`.
CORE_IMPORT = "data_director"
COMMAND = "uv run dd-gen-schema"

# The two documents that cross the transport each get a schema of their own.
CORE_DOCUMENTS = {
    "Envelope": "envelope.schema.json",
    "InvocationRequest": "invocation_request.schema.json",
}
SHACL = "data_director.shacl.ttl"
DESIGNATOR = "schema_class"
OPEN = "open"  # a class annotation: any object naming its class in schema_class
DRAFT_7 = "http://json-schema.org/draft-07/schema#"


def class_schema_name(class_name: str) -> str:
    return f"{class_name}.schema.json"


def class_shapes_name(class_name: str) -> str:
    return f"{class_name}.shacl.ttl"


def class_context_name(class_name: str) -> str:
    return f"{class_name}.context.jsonld"


def generate(source: Path = CORE) -> dict[Path, str]:
    """Every file generated from `source`, keyed by where it is written. Writes nothing."""
    source = source.resolve()
    out = source.parent / GENERATED
    core = source == CORE.resolve()
    outputs: dict[Path, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        importmap = Path(tmp) / "importmap.json"
        importmap.write_text(json.dumps({CORE_IMPORT: str(CORE.with_suffix(""))}), "utf-8")
        view = _view(source, importmap)
        classes = designated_classes(source, view)
        # Each generator run is its own Python process, most of whose time is importing LinkML,
        # so they run side by side; the outputs are assembled in a fixed order below.
        documents = list(CORE_DOCUMENTS) if core else []
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
            shacl = pool.submit(
                _run, "linkml.generators.shaclgen", *_imports(importmap), str(source)
            )
            generated = iter(
                pool.map(lambda top: _json_schema(source, top, importmap), documents + classes)
            )
            for top_class in documents:
                schema = next(generated)
                filename = CORE_DOCUMENTS[top_class]
                outputs[out / filename] = _dump(_repair(schema, top_class, view), source)
            shapes_text = shacl.result()
            if core:
                outputs[out / SHACL] = shapes_text
            class_schemas = list(generated)
        shapes = _graph(shapes_text) if classes else None
        for class_name, schema in zip(classes, class_schemas, strict=True):
            schema = _prune(_repair(schema, class_name, view))
            schema["$id"] = f"{view.schema.id}/{class_name}"
            # Validated as Draft 7 on both sides (dd_sdk.contract.classes, the viewer's ajv), so
            # it says so; LinkML's metamodel keys mean nothing to a JSON Schema consumer.
            schema["$schema"] = DRAFT_7
            for key in ("metamodel_version", "version"):
                schema.pop(key, None)
            schema["title"] = class_name
            # gen-json-schema leaves a top class open; a class schema is as closed as its
            # `$defs` are, as the Pydantic models are (extra="forbid").
            schema["additionalProperties"] = False
            outputs[out / class_schema_name(class_name)] = _dump(schema, source)
            assert shapes is not None
            iri = view.get_uri(class_name, expand=True)
            outputs[out / class_shapes_name(class_name)] = _class_shapes(shapes, iri)
            outputs[out / class_context_name(class_name)] = _class_context(view, class_name, schema)
    return outputs


def _imports(importmap: Path) -> tuple[str, str]:
    return ("--importmap", str(importmap))


def _graph(turtle: str) -> Any:
    from rdflib import Graph

    return Graph().parse(data=turtle, format="turtle")


def _class_shapes(shapes: Any, class_iri: str) -> str:
    """The node shape of `class_iri` and every node shape it reaches through `sh:class` or
    `sh:node`, with every triple below them, as Turtle: what a payload of the class is checked
    against, and nothing else."""
    from rdflib import BNode, Graph, URIRef
    from rdflib.namespace import RDF, SH

    kept = Graph(namespace_manager=shapes.namespace_manager)
    pending, seen = [URIRef(class_iri)], set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for s, p, o in shapes.triples((node, None, None)):
            kept.add((s, p, o))
            if isinstance(o, BNode) or (
                p in (SH["class"], SH.node) and (o, RDF.type, SH.NodeShape) in shapes
            ):
                pending.append(o)
    if (URIRef(class_iri), RDF.type, SH.NodeShape) not in kept:
        raise ValueError(f"no SHACL node shape for {class_iri}")
    text: str = kept.serialize(format="turtle")
    return text


def _class_context(view: Any, class_name: str, schema: dict[str, Any]) -> str:
    """The JSON-LD context that reads a document of the class as RDF: every prefix, the class and
    each class in its `$defs` by its URI, and each of their slots by its slot URI. A URI is read
    as an IRI, and a literal of a type other than string, integer or boolean is typed as the shapes
    expect. A key no slot names falls to the source's default prefix, where a closed shape reports
    it. The harness names each
    object's class with `@type` (dd_sdk.contract.rdf), so the shapes find their targets.

    Built from the schema view rather than by gen-jsonld-context, which refuses a source that
    redefines a core slot, as several agents do (`title`)."""
    namespaces = {str(k): str(v) for k, v in view.namespaces().items()}
    context: dict[str, Any] = dict(namespaces)
    context["@vocab"] = namespaces[view.schema.default_prefix]
    classes = view.all_classes()
    reached = [class_name, *(c for c in schema.get("$defs", {}) if c in classes)]
    for name in reached:
        context[name] = {"@id": view.get_uri(name, expand=True)}
    for name in reached:
        for slot in view.class_induced_slots(name):
            term: dict[str, str] = {"@id": view.get_uri(slot, expand=True)}
            if slot.range in classes:
                term["@type"] = "@id"  # an inlined object is a node; a reference names one
            elif slot.range in view.all_types():
                uri = view.get_uri(view.get_type(slot.range), expand=True)
                if uri == _ANY_URI:
                    term["@type"] = "@id"  # the shapes take a URI slot's value as an IRI node
                elif uri not in _NATIVE:
                    term["@type"] = uri
            if context.get(slot.name, term) != term:
                raise ValueError(
                    f"{class_name}: slot {slot.name!r} has two meanings in the classes it reaches"
                )
            context[slot.name] = term
    return json.dumps({"@context": context}, indent=3, sort_keys=True) + "\n"


_ANY_URI = "http://www.w3.org/2001/XMLSchema#anyURI"
# Literal types a JSON value already carries: JSON-LD reads strings, integers and booleans as these.
_NATIVE = frozenset(
    "http://www.w3.org/2001/XMLSchema#" + t for t in ("string", "integer", "boolean")
)


def designated_classes(source: Path, view: Any) -> list[str]:
    """The concrete classes `source` itself defines that carry the `schema_class` designator."""
    own = view.all_classes(imports=False)
    return [
        c
        for c in own
        if not view.get_class(c).abstract
        and DESIGNATOR in {s.name for s in view.class_induced_slots(c)}
    ]


def _open_classes(view: Any) -> set[str]:
    """Classes annotated `open: true`: the core's `Input` and `Payload` (docs/specs/contract.md)."""
    found = set()
    for name, cls in view.all_classes().items():
        note = cls.annotations.get(OPEN) if cls.annotations else None
        if note is not None and str(note.value).lower() == "true":
            found.add(name)
    return found


def _view(source: Path, importmap: Path) -> Any:
    from linkml_runtime.utils.schemaview import SchemaView

    return SchemaView(str(source), importmap=json.loads(importmap.read_text("utf-8")))


def _run(module: str, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", module, *args], check=True, capture_output=True, text=True
    )
    return result.stdout


def _json_schema(source: Path, top_class: str, importmap: Path) -> dict[str, Any]:
    text = _run(
        "linkml.generators.jsonschemagen",
        "--top-class",
        top_class,
        "--importmap",
        str(importmap),
        str(source),
    )
    schema: dict[str, Any] = json.loads(text)
    return schema


def _repair(schema: dict[str, Any], top_class: str, view: Any) -> dict[str, Any]:
    """Four repairs to the generator's output, made in the one place generation happens.

    1. `requires_human_review` is emitted as `const: true`. LinkML's `equals_expression` is not
       carried into JSON Schema by gen-json-schema. C13/C15 make human review mandatory; a
       consumer in another language must be unable to produce an envelope that claims otherwise.
    2. A polymorphic slot (`range: Any` + `any_of`) that is required is emitted as
       `{"$ref": "#/$defs/Any", "anyOf": [...]}`. Under Draft 7, `$ref` overrides every sibling
       keyword, so the `anyOf` would never be checked and any object would validate. The `$ref`
       is dropped; the `anyOf` alone is the constraint (docs/specs/contract.md).
    3. Properties are emitted in alphabetical order. They are put back in the order the LinkML
       source gives a class's slots, own slots before mixins, which is the order a reader meets
       them in the viewer (docs/specs/agents.md). Property order carries no meaning in JSON Schema.
    4. A class annotated `open: true` is emitted closed, with its designator fixed to its own
       name. LinkML cannot say "any object that names its class". It is opened: any further
       property is allowed, and `schema_class` is any string. The agent's class schema checks
       the rest (docs/specs/contract.md).
    """
    holders = [(top_class, schema), *schema.get("$defs", {}).items()]
    classes = view.all_classes()
    opened = _open_classes(view)
    for class_name, holder in holders:
        properties = holder.get("properties", {})
        if class_name in opened:
            holder["additionalProperties"] = True
            properties.get(DESIGNATOR, {}).pop("enum", None)
        for name, prop in properties.items():
            if name == "requires_human_review":
                prop["const"] = True
            if "anyOf" in prop and prop.get("$ref", "").endswith("/Any"):
                del prop["$ref"]
        if properties and class_name in classes:
            order = [s.name for s in view.class_induced_slots(class_name)]
            rank = {name: i for i, name in enumerate(order)}
            holder["properties"] = dict(
                sorted(properties.items(), key=lambda kv: rank.get(kv[0], len(order)))
            )
    return schema


def _refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            yield ref.removeprefix("#/$defs/")
        for key, value in node.items():
            if key != "$defs":
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def _prune(schema: dict[str, Any]) -> dict[str, Any]:
    """Keep only the `$defs` the top class reaches, so a class schema carries what it needs."""
    defs = schema.get("$defs", {})
    reached: set[str] = set()
    pending = list(_refs(schema))
    while pending:
        name = pending.pop()
        if name in reached or name not in defs:
            continue
        reached.add(name)
        pending.extend(_refs(defs[name]))
    schema["$defs"] = {name: defs[name] for name in defs if name in reached}
    if not schema["$defs"]:
        del schema["$defs"]
    return schema


def _dump(schema: dict[str, Any], source: Path) -> str:
    # The source's name only, so the output does not depend on where the command was run.
    command = COMMAND if source == CORE.resolve() else f"{COMMAND} <path to {source.name}>"
    schema = {"$comment": f"Generated from {source.name} by `{command}`. Do not edit.", **schema}
    return json.dumps(schema, indent=3) + "\n"


def stale(source: Path = CORE) -> list[str]:
    """What in `generated/` beside `source` is out of date: missing, different, or no longer
    generated. Empty when current. A SHACL file is compared as a graph, since rdflib
    does not serialise blank nodes in a stable order. An agent's tests call this for its own
    LinkML file, as `sdk/tests/test_contract.py` does for the core."""
    outputs = generate(source)
    found: list[str] = []
    for path, content in outputs.items():
        if not path.exists():
            found.append(f"{path.name} is missing")
        elif not _same(path, path.read_text(encoding="utf-8"), content):
            found.append(f"{path.name} is stale")
    directory = source.resolve().parent / GENERATED
    left = (
        sorted(p.name for p in directory.iterdir() if p not in outputs)
        if directory.is_dir()
        else []
    )
    found.extend(f"{name} is no longer generated" for name in left)
    return found


def _same(path: Path, current: str, fresh: str) -> bool:
    if path.suffix != ".ttl":
        return current == fresh
    from rdflib import Graph
    from rdflib.compare import to_isomorphic

    graphs = [to_isomorphic(Graph().parse(data=text, format="turtle")) for text in (current, fresh)]
    same: bool = graphs[0] == graphs[1]
    return same


def write(outputs: dict[Path, str]) -> None:
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")  # noqa: T201 — a command-line tool reports what it wrote


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-gen-schema",
        description="Regenerate JSON Schema from a LinkML source: the core contract by default, "
        "or an agent's own classes.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=CORE,
        help="a LinkML file (default: the core contract, dd_sdk/schema/data_director.yaml)",
    )
    args = parser.parse_args(argv)
    try:
        import linkml_runtime  # noqa: F401 — present only with the development dependencies
    except ImportError:
        sys.exit("dd-gen-schema needs LinkML: run `uv sync --all-packages --all-extras`")
    if not args.source.is_file():
        sys.exit(f"{args.source}: no such LinkML file")
    write(generate(args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
