"""Regenerate src/dd_sdk/schema/generated/ from src/dd_sdk/schema/data_director.yaml.

Run after any change to the LinkML source. tests/test_schema_current.py byte-compares the output,
so a hand edit to a generated file fails the suite rather than taking effect.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "src" / "dd_sdk" / "schema"
SOURCE = SCHEMA / "data_director.yaml"
OUT = SCHEMA / "generated"

# The JSON Schema needs a top class; the request and the envelope are the two documents that
# cross the transport, so each gets its own file.
TOP_CLASSES = {
    "Envelope": "envelope.schema.json",
    "InvocationRequest": "invocation_request.schema.json",
}
SHACL = "data_director.shacl.ttl"


def generate() -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    for top_class, filename in TOP_CLASSES.items():
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "linkml.generators.jsonschemagen",
                "--top-class",
                top_class,
                str(SOURCE),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        outputs[OUT / filename] = _pin_constants(result.stdout)
    result = subprocess.run(
        [sys.executable, "-m", "linkml.generators.shaclgen", str(SOURCE)],
        check=True,
        capture_output=True,
        text=True,
    )
    outputs[OUT / SHACL] = result.stdout
    return outputs


def _pin_constants(schema_text: str) -> str:
    """Two repairs to the generator's output, made in the one place generation happens.

    1. `requires_human_review` is emitted as `const: true`. LinkML's `equals_expression` is not
       carried into JSON Schema by gen-json-schema. C13/C15 make human review mandatory; a
       consumer in another language must be unable to produce an envelope that claims otherwise.
    2. A polymorphic slot (`range: Any` + `any_of`) that is required is emitted as
       `{"$ref": "#/$defs/Any", "anyOf": [...]}`. Under Draft 7, `$ref` overrides every sibling
       keyword, so the `anyOf` would never be checked and any object would validate. The `$ref`
       is dropped; the `anyOf` alone is the constraint (ADR-0007).
    """
    schema = json.loads(schema_text)
    for holder in (schema, *schema.get("$defs", {}).values()):
        for name, prop in holder.get("properties", {}).items():
            if name == "requires_human_review":
                prop["const"] = True
            if "anyOf" in prop and prop.get("$ref", "").endswith("/Any"):
                del prop["$ref"]
    return json.dumps(schema, indent=3) + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for path, content in generate().items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
