"""The pandoc helpers scripts/blueprint/convert.py builds on: running pandoc, and reading and
making the elements of its JSON abstract syntax tree."""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Any

# A pandoc AST element and a list of them, as pandoc's JSON gives them.
Node = dict[str, Any]
Nodes = list[Any]


def pandoc(args: list[str], stdin: str) -> str:
    try:
        result = subprocess.run(
            ["pandoc", *args], input=stdin, capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        sys.exit("convert.py: pandoc is not on PATH")
    except subprocess.CalledProcessError as error:
        sys.exit(f"convert.py: pandoc failed:\n{error.stderr}")
    return result.stdout


# The text of the inlines that hold none of their own: a space for a break, nothing for a note.
FIXED_TEXT = {"Space": " ", "SoftBreak": " ", "LineBreak": " ", "Note": ""}


def text(node: object) -> str:
    """The plain text of an inline or block tree, without footnotes."""
    if isinstance(node, list):
        return "".join(text(item) for item in node)
    if not isinstance(node, dict):
        return ""
    kind = node.get("t")
    if kind == "Str":
        return str(node["c"])
    if kind in FIXED_TEXT:
        return FIXED_TEXT[kind]
    if kind in ("Link", "Image", "Span", "Code"):
        return text(node["c"][1])
    return text(node.get("c", []))


def str_node(value: str) -> Node:
    return {"t": "Str", "c": value}


def raw_html(value: str) -> Node:
    return {"t": "RawInline", "c": ["html", value]}


def link(inlines: Nodes, url: str) -> Node:
    return {"t": "Link", "c": [["", [], []], inlines, [url, ""]]}


def github_slug(heading: str) -> str:
    """The anchor GitHub gives a heading."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug)
    return slug.replace(" ", "-")
