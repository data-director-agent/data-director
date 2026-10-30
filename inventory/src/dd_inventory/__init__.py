"""Describe a dataset's files where they live, without sending them anywhere (ADR-0034).

`dd-inventory ROOT` walks a folder and writes a `FileInventory`: for each file its path relative
to ROOT, its size, its SHA-256 digest, its format identified against PRONOM, and for a table its
fields. The inventory holds facts about the files and never their content.
"""

from dd_inventory.scan import TOOL, make_inventory, tool_version

__all__ = ["TOOL", "make_inventory", "tool_version"]
