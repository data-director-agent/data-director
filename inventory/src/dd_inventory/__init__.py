"""Describe a dataset's files where they live, without sending them anywhere
(docs/specs/projects.md).

`dd-inventory ROOT` walks a folder and writes a `FileInventory`: for each file its path relative
to ROOT, its size, its SHA-256 digest, its format identified against PRONOM, and for a table its
fields. The inventory holds facts about the files and never their content. Given several folders,
`dd-inventory A B` makes one inventory with a part for each (`make_inventory_of`).
"""

from dd_inventory.scan import (
    TOOL,
    FileProgress,
    detect_runtime,
    make_inventory,
    make_inventory_of,
    tool_version,
)

__all__ = [
    "TOOL",
    "FileProgress",
    "detect_runtime",
    "make_inventory",
    "make_inventory_of",
    "tool_version",
]
