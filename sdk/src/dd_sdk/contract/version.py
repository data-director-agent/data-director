"""The contract version, and which agents the workbench can govern under it (ADR-0019).

The contract version is the `version` of the core LinkML schema, `schema/data_director.yaml`,
read from the generated envelope schema so that no YAML parser is needed at runtime. An agent
card declares the version its agent was built against. The workbench governs an agent whose
version has the same major version as its own and, while the major version is 0, the same minor
version (the caret rule). Any other agent is incompatible, which is reported as such, not as
unavailable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_ENVELOPE_SCHEMA = (
    Path(__file__).resolve().parents[1] / "schema" / "generated" / "envelope.schema.json"
)
_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

CONTRACT_VERSION: str = json.loads(_ENVELOPE_SCHEMA.read_text(encoding="utf-8"))["version"]


def _parts(version: str) -> tuple[int, int, int] | None:
    match = _VERSION.match(version)
    if match is None:
        return None
    major, minor, patch = (int(p) for p in match.groups())
    return major, minor, patch


def compatible(declared: str, current: str = CONTRACT_VERSION) -> bool:
    """Whether an agent built against contract `declared` can be governed under `current`."""
    ours, theirs = _parts(current), _parts(declared)
    if ours is None or theirs is None:
        return False
    if ours[0] != theirs[0]:
        return False
    return ours[0] != 0 or ours[1] == theirs[1]
