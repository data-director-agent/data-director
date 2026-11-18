"""The browser bundle's stand-in for spaCy is enough for the detector: with it in spaCy's place,
the command makes the same inventory as with spaCy (inventory/browser/README.md, #470).

Presidio imports spaCy at module level; the bundle cannot hold spaCy, so it holds a stub. A
Presidio release that imports more of spaCy fails here before it reaches the browser.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STUB = Path(__file__).parents[1] / "browser" / "bundle" / "spacy-stub"
SAMPLE = Path(__file__).parent / "data" / "disclosure" / "direct"

SCAN = """
import json, sys
from pathlib import Path
if sys.argv[1]:
    sys.path.insert(0, sys.argv[1])
import spacy
from dd_inventory import make_inventory
inventory = make_inventory(Path(sys.argv[2]))
print(json.dumps({"stub": spacy.__version__.endswith("+stub"), "inventory": inventory}))
"""


def _scan(stub: Path | None) -> dict[str, object]:
    done = subprocess.run(
        [sys.executable, "-c", SCAN, str(stub or ""), str(SAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    result: dict[str, object] = json.loads(done.stdout)
    return result


def _without_time(inventory: object) -> object:
    assert isinstance(inventory, dict)
    return {k: v for k, v in inventory.items() if k != "inventory_made_at"}


def test_the_detector_finds_the_same_with_the_stub_as_with_spacy() -> None:
    stubbed, real = _scan(STUB), _scan(None)
    assert stubbed["stub"] is True
    assert real["stub"] is False
    assert _without_time(stubbed["inventory"]) == _without_time(real["inventory"])
