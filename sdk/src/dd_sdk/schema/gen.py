"""Generate JSON Schema (and, for the core, SHACL) from a LinkML source (ADR-0019).

`dd-gen-schema` with no argument regenerates the core contract, `data_director.yaml`, into
`generated/` beside it: the envelope and request schemas, the SHACL shapes, and one class schema
for each core class that carries `schema_class`. `dd-gen-schema PATH` does the same for an
agent's own LinkML file, which imports the core as `data_director`: one class schema for each of
its classes that carries `schema_class`, written to `generated/` beside `PATH`.

A class schema is self-contained: its `$defs` hold only the definitions the class reaches. Its
`$comment` names the source and the command, and the tests byte-compare every generated file
against a fresh generation, so a hand edit fails the suite rather than taking effect.

LinkML is a development dependency (ADR-0007): it is needed to regenerate a schema, never to
load one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Iterator
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


def class_schema_name(class_name: str) -> str:
    return f"{class_name}.schema.json"


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
        if core:
            for top_class, filename in CORE_DOCUMENTS.items():
                schema = _json_schema(source, top_class, importmap)
                outputs[out / filename] = _dump(_repair(schema, top_class, view), source)
            outputs[out / SHACL] = _run("linkml.generators.shaclgen", str(source))
        for class_name in designated_classes(source, view):
            schema = _json_schema(source, class_name, importmap)
            schema = _prune(_repair(schema, class_name, view))
            schema["$id"] = f"{view.schema.id}/{class_name}"
            schema["title"] = class_name
            # gen-json-schema leaves a top class open; a class schema is as closed as its
            # `$defs` are, as the Pydantic models are (extra="forbid").
            schema["additionalProperties"] = False
            outputs[out / class_schema_name(class_name)] = _dump(schema, source)
    return outputs


def designated_classes(source: Path, view: Any) -> list[str]:
    """The classes `source` itself defines that carry the `schema_class` designator."""
    own = view.all_classes(imports=False)
    return [c for c in own if DESIGNATOR in {s.name for s in view.class_induced_slots(c)}]


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
    """Three repairs to the generator's output, made in the one place generation happens.

    1. `requires_human_review` is emitted as `const: true`. LinkML's `equals_expression` is not
       carried into JSON Schema by gen-json-schema. C13/C15 make human review mandatory; a
       consumer in another language must be unable to produce an envelope that claims otherwise.
    2. A polymorphic slot (`range: Any` + `any_of`) that is required is emitted as
       `{"$ref": "#/$defs/Any", "anyOf": [...]}`. Under Draft 7, `$ref` overrides every sibling
       keyword, so the `anyOf` would never be checked and any object would validate. The `$ref`
       is dropped; the `anyOf` alone is the constraint (ADR-0007).
    3. Properties are emitted in alphabetical order. They are put back in the order the LinkML
       source gives a class's slots, own slots before mixins, which is the order a reader meets
       them in the viewer (ADR-0016). Property order carries no meaning in JSON Schema.
    """
    holders = [(top_class, schema), *schema.get("$defs", {}).items()]
    classes = view.all_classes()
    for class_name, holder in holders:
        properties = holder.get("properties", {})
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
