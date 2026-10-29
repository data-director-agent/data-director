# /// script
# requires-python = ">=3.12"
# ///
"""Build the chaptered Markdown edition of the Blueprint in docs/blueprint/.

The input is a pandoc-readable conversion of the Blueprint's Word original (the former
docs/BLUEPRINT.md, recoverable with `git show acf68a6:docs/BLUEPRINT.md`). It holds the document's
real structure: headings, emphasis, links, footnotes and table cells. The published PDF is the
authority for the words; scripts/blueprint/check_text.py compares the output with it.

Usage:
    uv run scripts/blueprint/convert.py SOURCE.md [--out docs/blueprint]

Requires pandoc on PATH. The figures are not converted: each is a hand transcription in
scripts/blueprint/figures/figure-N.mmd, placed where the source has the image.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

# The chapter and appendix files, keyed by the number or letter that opens the heading.
CHAPTER_FILES = {
    "1": "01-executive-summary.md",
    "2": "02-introduction.md",
    "3": "03-problem-definition.md",
    "4": "04-research-context.md",
    "5": "05-blueprint-considerations.md",
    "6": "06-architecture-principles.md",
    "7": "07-functional-specification.md",
    "8": "08-process-flow.md",
    "9": "09-reference-architecture.md",
    "10": "10-evaluation-criteria.md",
    "11": "11-implementation-guidance.md",
    "12": "12-blueprint-governance.md",
    "13": "13-open-questions.md",
    "A": "appendix-a-glossary.md",
    "B": "appendix-b-related-resources.md",
    "C": "appendix-c-acknowledgements.md",
    "D": "appendix-d-implementors.md",
    "E": "appendix-e-tool-usage.md",
    "F": "appendix-f-partners.md",
    "G": "appendix-g-comment-log.md",
}
INDEX_FILE = "README.md"
# "14. Appendices" is a heading with no text of its own; the index lists the appendices under it.
APPENDICES_HEADING = "14. Appendices"

# Paragraphs of the source's front matter that describe the source, not the Blueprint.
DROP_FRONT_MATTER = (
    "# Data Director Agentic AI Tool Blueprint",
    "Retrieved from ",
    "The Blueprint has since been officially adopted",
)

# The one change between the August 2026 final and the endorsed PDF besides the cover pages and
# page numbers: an ORCID added to author 43. (row number, column index, text)
ENDORSED_PATCHES = [("43", 6, "0000-0002-5931-072X")]

REQUIREMENT_ID = re.compile(r"^([RC]\d+)$")
XREF_WORD = re.compile(r"^(\W*)(Section|Sections|Table|Figure|Appendix)$")
XREF_TARGET = re.compile(r"^(\d+(?:\.\d+)*|[A-G])(?![\w])(.*)$")

# A pandoc AST element and a list of them, as pandoc's JSON gives them.
Node = dict[str, Any]
Nodes = list[Any]
# An inline list in, an inline list out.
InlineFn = Callable[[Nodes], Nodes]
# A link target: (file, anchor, whether the anchor is the file's own title).
Target = tuple[str, str, bool]


# --- pandoc AST helpers --------------------------------------------------------------------------


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


def text(node: object) -> str:
    """The plain text of an inline or block tree, without footnotes."""
    if isinstance(node, list):
        return "".join(text(item) for item in node)
    if not isinstance(node, dict):
        return ""
    kind = node.get("t")
    if kind == "Str":
        return str(node["c"])
    if kind in ("Space", "SoftBreak", "LineBreak"):
        return " "
    if kind == "Note":
        return ""
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


# --- inline clean-up -----------------------------------------------------------------------------


def strip_wrappers(inlines: Nodes) -> Nodes:
    """Drop Word's underline on links and its highlight spans, keeping their text."""
    out = []
    for node in inlines:
        if node.get("t") == "Underline":
            out.extend(strip_wrappers(node["c"]))
        elif node.get("t") == "Span":
            out.extend(strip_wrappers(node["c"][1]))
        else:
            out.append(walk_inline_children(node, strip_wrappers))
    return out


def walk_inline_children(node: Node, fn: InlineFn) -> Node:
    kind = node.get("t")
    content: Any = node.get("c")
    if kind in ("Emph", "Strong", "Strikeout", "Superscript", "Subscript", "SmallCaps"):
        return {"t": kind, "c": fn(content)}
    if kind in ("Link", "Image"):
        return {"t": kind, "c": [content[0], fn(content[1]), content[2]]}
    if kind == "Span":
        return {"t": kind, "c": [content[0], fn(content[1])]}
    if kind == "Quoted":
        return {"t": kind, "c": [content[0], fn(content[1])]}
    if kind == "Note":
        return {"t": kind, "c": walk_blocks(content, fn)}
    return node


def walk_blocks(blocks: Nodes, fn: InlineFn, headers: bool = True) -> Nodes:
    """Apply an inline-list function to every inline list in a block list."""
    out = []
    for block in blocks:
        kind = block["t"]
        content = block.get("c")
        if kind in ("Para", "Plain"):
            out.append({"t": kind, "c": fn(content)})
        elif kind == "Header" and headers:
            out.append({"t": kind, "c": [content[0], content[1], fn(content[2])]})
        elif kind in ("BulletList",):
            out.append({"t": kind, "c": [walk_blocks(item, fn) for item in content]})
        elif kind == "OrderedList":
            out.append({"t": kind, "c": [content[0], [walk_blocks(i, fn) for i in content[1]]]})
        elif kind == "BlockQuote":
            out.append({"t": kind, "c": walk_blocks(content, fn)})
        elif kind == "Table":
            out.append(walk_table(block, lambda cell: walk_blocks(cell, fn)))
        else:
            out.append(block)
    return out


def walk_table(table: Node, fn: InlineFn) -> Node:
    attr, caption, specs, head, bodies, foot = table["c"]

    def rows(rs: Nodes) -> Nodes:
        return [[r[0], [[c[0], c[1], c[2], c[3], fn(c[4])] for c in r[1]]] for r in rs]

    head = [head[0], rows(head[1])]
    bodies = [[b[0], b[1], rows(b[2]), rows(b[3])] for b in bodies]
    foot = [foot[0], rows(foot[1])]
    return {"t": "Table", "c": [attr, caption, specs, head, bodies, foot]}


# --- tables --------------------------------------------------------------------------------------


def cell_inlines(blocks: Nodes) -> Nodes:
    """Flatten a table cell to one line of inlines, with <br> where the cell had breaks."""
    parts: list[Nodes] = []
    for block in blocks:
        kind = block["t"]
        if kind in ("Para", "Plain"):
            parts.append(block["c"])
        elif kind == "BulletList":
            parts.extend(
                [str_node("•"), {"t": "Space"}, *cell_inlines(item)] for item in block["c"]
            )
        elif kind == "OrderedList":
            start = block["c"][0][0]
            parts.extend(
                [str_node(f"{start + n}."), {"t": "Space"}, *cell_inlines(item)]
                for n, item in enumerate(block["c"][1])
            )
        else:
            sys.exit(f"convert.py: unexpected {kind} in a table cell")
    out: Nodes = []
    for part in parts:
        if out:
            out.append(raw_html("<br>"))
        out.extend(part)
    return line_breaks_to_html(out)


def line_breaks_to_html(inlines: Nodes) -> Nodes:
    """<br> for each hard line break, however deeply nested, so the cell stays on one line."""
    return [
        raw_html("<br>")
        if node.get("t") == "LineBreak"
        else walk_inline_children(node, line_breaks_to_html)
        for node in inlines
    ]


def is_description_row(cells: Nodes) -> bool:
    """A second header row: each filled cell is entirely italic, as under Table 4's titles."""
    filled = [c[4] for c in cells if text(c[4]).strip()]
    if not filled:
        return False
    for blocks in filled:
        if len(blocks) != 1 or blocks[0]["t"] not in ("Para", "Plain"):
            return False
        inlines = [n for n in blocks[0]["c"] if n.get("t") not in ("Space", "SoftBreak")]
        if not all(n.get("t") == "Emph" for n in inlines):
            return False
    return True


def convert_table(table: Node) -> Node:
    """A GFM pipe table: one-line cells, the first row (and its description row) as header."""
    attr, _caption, specs, head, bodies, foot = table["c"]
    rows = list(head[1])
    for body in bodies:
        rows.extend(body[2])
        rows.extend(body[3])
    rows.extend(foot[1])
    if len(specs) == 1 and len(rows) == 1:
        # A one-cell table is a boxed note in the PDF.
        return {"t": "BlockQuote", "c": rows[0][1][0][4]}

    def plain(cell: Nodes, inlines: Nodes) -> Nodes:
        blocks = [{"t": "Plain", "c": inlines}] if inlines else []
        return [cell[0], {"t": "AlignDefault"}, 1, 1, blocks]

    header = [[c, cell_inlines(c[4])] for c in rows[0][1]]
    body_rows = rows[1:]
    if body_rows and is_description_row(body_rows[0][1]):
        for slot, cell in zip(header, body_rows[0][1], strict=True):
            extra = cell_inlines(cell[4])
            if extra:
                slot[1] = [*slot[1], raw_html("<br>"), *extra] if slot[1] else extra
        body_rows = body_rows[1:]
    head_row = [["", [], []], [plain(c, inl) for c, inl in header]]
    new_rows = [[r[0], [plain(c, cell_inlines(c[4])) for c in r[1]]] for r in body_rows]
    specs = [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}] for _ in specs]
    return {
        "t": "Table",
        "c": [
            attr,
            [None, []],
            specs,
            [["", [], []], [head_row]],
            [[["", [], []], 0, [], new_rows]],
            [["", [], []], []],
        ],
    }


def apply_endorsed_patches(table: Node) -> int:
    applied = 0
    for body in table["c"][4]:
        for row in body[3]:
            cells = row[1]
            for number, column, value in ENDORSED_PATCHES:
                if (
                    text(cells[0][4]).strip() == number
                    and len(cells) > column
                    and not text(cells[column][4]).strip()
                ):
                    cells[column][4] = [{"t": "Plain", "c": [str_node(value)]}]
                    applied += 1
    return applied


def anchor_requirements(table: Node) -> list[str]:
    """Put <a id="r3"></a> before each requirement identifier in a requirements table."""
    found = []
    for body in table["c"][4]:
        for row in body[3]:
            first = row[1][0]
            match = REQUIREMENT_ID.match(text(first[4]).strip())
            if match and first[4] and first[4][0]["t"] in ("Para", "Plain"):
                ident = match.group(1)
                first[4][0]["c"].insert(0, raw_html(f'<a id="{ident.lower()}"></a>'))
                found.append(ident)
    return found


# --- figures -------------------------------------------------------------------------------------


def replace_images(blocks: Nodes, counter: list[int]) -> Nodes:
    """Swap each image for a placeholder that the Mermaid transcription replaces."""
    out = []
    for block in blocks:
        if block["t"] == "Para" and any(n.get("t") == "Image" for n in block["c"]):
            before: Nodes = []
            after: Nodes = []
            seen = False
            for node in block["c"]:
                if node.get("t") == "Image":
                    seen = True
                    continue
                (after if seen else before).append(node)
            counter[0] += 1
            if text(before).strip():
                out.append({"t": "Para", "c": before})
            out.append({"t": "Para", "c": [str_node(f"@@FIGURE-{counter[0]}@@")]})
            if text(after).strip():
                out.append({"t": "Para", "c": after})
        else:
            out.append(block)
    return out


def caption_anchor(block: Node) -> str | None:
    """'table-5' for a paragraph opening with a bold "Table 5" caption label."""
    if block["t"] != "Para" or not block["c"] or block["c"][0].get("t") != "Strong":
        return None
    match = re.fullmatch(r"(Table|Figure) (\d+)\.?", text(block["c"][0]).strip())
    return f"{match.group(1).lower()}-{match.group(2)}" if match else None


# --- splitting and cross-references --------------------------------------------------------------


def heading_key(heading: str) -> str | None:
    match = re.match(r"^(?:(\d+)\.\s|Appendix ([A-G]):)", heading.strip())
    if not match:
        return None
    return match.group(1) or match.group(2)


def split(blocks: Nodes) -> dict[str, Nodes]:
    """Assign blocks to files. Level-1 chapters and level-2 appendices each start a file."""
    files: dict[str, Nodes] = {INDEX_FILE: []}
    current: str | None = INDEX_FILE
    for block in blocks:
        if block["t"] == "Header":
            level, heading = block["c"][0], text(block["c"][2]).strip()
            if not heading:
                continue
            key = heading_key(heading)
            if heading == APPENDICES_HEADING:
                current = None
                continue
            if key and ((key.isdigit() and level == 1) or (key.isalpha() and level == 2)):
                current = CHAPTER_FILES[key]
                files[current] = []
            if current is None:
                sys.exit(f"convert.py: text under '{APPENDICES_HEADING}' before Appendix A")
            if current.startswith("appendix-"):
                block = {"t": "Header", "c": [level - 1, *block["c"][1:]]}
        elif current is None:
            sys.exit(f"convert.py: text under '{APPENDICES_HEADING}' before Appendix A")
        files[current].append(block)
    return files


def build_targets(
    files: dict[str, Nodes],
) -> tuple[dict[str, Target], dict[tuple[str, str], Target]]:
    """Map each source heading id, section number, table and figure to where it now is."""
    by_id: dict[str, Target] = {}
    by_ref: dict[tuple[str, str], Target] = {}
    for name, blocks in files.items():
        seen: dict[str, int] = {}
        for block in blocks:
            if block["t"] == "Header":
                heading = text(block["c"][2]).strip()
                slug = github_slug(heading)
                if slug in seen:
                    seen[slug] += 1
                    slug = f"{slug}-{seen[slug]}"
                else:
                    seen[slug] = 0
                target = (name, slug, block["c"][0] == 1)
                by_id[block["c"][1][0]] = target
                match = re.match(r"^(\d+(?:\.\d+)*)\.?\s", heading)
                if match:
                    by_ref[("Section", match.group(1))] = target
                match = re.match(r"^Appendix ([A-G]):", heading)
                if match:
                    by_ref[("Appendix", match.group(1))] = target
            anchor = caption_anchor(block)
            if anchor:
                kind, number = anchor.split("-")
                by_ref[(kind.title(), number)] = (name, anchor, False)
    return by_id, by_ref


def relative(target: Target, here: str) -> str:
    """The link from file `here`: an anchor within it, or another file (at its anchor)."""
    name, anchor, is_title = target
    if name == here:
        return f"#{anchor}"
    return name if is_title else f"{name}#{anchor}"


def link_xrefs(inlines: Nodes, by_ref: dict[tuple[str, str], Target], here: str) -> Nodes:
    """Link "Section 7.1", "Table 5", "Figure 2" and "Appendix C"; the words stay as printed."""
    out: Nodes = []
    i = 0
    while i < len(inlines):
        node = inlines[i]
        word = XREF_WORD.match(node["c"]) if node.get("t") == "Str" else None
        if (
            word
            and i + 2 < len(inlines)
            and inlines[i + 1].get("t") == "Space"
            and inlines[i + 2].get("t") == "Str"
        ):
            prefix, name = word.groups()
            match = XREF_TARGET.match(inlines[i + 2]["c"])
            kind = {"Sections": "Section"}.get(name, name)
            if match and (kind, match.group(1)) in by_ref:
                url = relative(by_ref[(kind, match.group(1))], here)
                if prefix:
                    out.append(str_node(prefix))
                out.append(link([str_node(name), {"t": "Space"}, str_node(match.group(1))], url))
                if match.group(2):
                    out.append(str_node(match.group(2)))
                i += 3
                continue
        if node.get("t") in ("Emph", "Quoted"):
            node = walk_inline_children(node, lambda xs: link_xrefs(xs, by_ref, here))
        elif node.get("t") == "Note":
            node = {
                "t": "Note",
                "c": walk_blocks(node["c"], lambda xs: link_xrefs(xs, by_ref, here)),
            }
        out.append(node)
        i += 1
    return out


def retarget_links(inlines: Nodes, by_id: dict[str, Target], here: str) -> Nodes:
    out = []
    for node in inlines:
        node = walk_inline_children(node, lambda xs: retarget_links(xs, by_id, here))
        if node.get("t") == "Link" and node["c"][2][0].startswith("#"):
            ident = node["c"][2][0][1:]
            if ident not in by_id:
                sys.exit(f"convert.py: link to unknown heading #{ident}")
            node["c"][2] = [relative(by_id[ident], here), node["c"][2][1]]
        out.append(node)
    return out


# --- writing -------------------------------------------------------------------------------------


def write_markdown(blocks: Nodes, api: Nodes) -> str:
    doc = json.dumps({"pandoc-api-version": api, "meta": {}, "blocks": blocks})
    return pandoc(["-f", "json", "-t", "gfm", "--wrap=none"], doc)


def renumber_notes(markdown: str, offset: int) -> tuple[str, int]:
    numbers = {int(n) for n in re.findall(r"\[\^(\d+)\]", markdown)}
    out = re.sub(r"\[\^(\d+)\]", lambda m: f"[^{int(m.group(1)) + offset}]", markdown)
    return out, len(numbers)


def figure_markdown(number: int) -> str:
    path = HERE / "figures" / f"figure-{number}.mmd"
    if not path.exists():
        sys.exit(f"convert.py: missing {path.relative_to(HERE.parent.parent)}")
    return f"```mermaid\n{path.read_text().rstrip()}\n```"


def contents(files: dict[str, Nodes]) -> str:
    lines = ["## Contents", ""]
    for name, blocks in files.items():
        if name == INDEX_FILE:
            continue
        if name == CHAPTER_FILES["A"]:
            lines.append(f"- {APPENDICES_HEADING}")
        indent = "  " if name.startswith("appendix-") else ""
        for block in blocks:
            if block["t"] != "Header":
                continue
            level, heading = block["c"][0], text(block["c"][2]).strip()
            target = name if level == 1 else f"{name}#{github_slug(heading)}"
            lines.append(f"{indent}{'  ' * (level - 1)}- [{heading}]({target})")
    return "\n".join(lines)


GENERATED = (
    "<!-- Generated by scripts/blueprint/convert.py from the Blueprint's Word original and "
    "checked against the published PDF by scripts/blueprint/check_text.py. Do not edit by hand. -->"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=Path("docs/blueprint"))
    args = parser.parse_args()

    ast = json.loads(pandoc(["-f", "markdown", "-t", "json"], args.source.read_text()))
    api, blocks = ast["pandoc-api-version"], ast["blocks"]

    # Front matter: everything before the first chapter heading.
    first = next(i for i, b in enumerate(blocks) if b["t"] == "Header" and b["c"][0] == 1)
    front = [
        b
        for b in blocks[:first]
        if not (b["t"] == "Para" and text(b["c"]).startswith(DROP_FRONT_MATTER))
    ]
    # The table of contents: the heading paragraph and its links. The index writes its own.
    toc_start = next(i for i, b in enumerate(front) if text(b.get("c", [])) == "Table of Contents")
    toc_end = next(i for i, b in enumerate(front) if text(b.get("c", [])) == "Document Control")
    front = front[:toc_start] + front[toc_end:]
    blocks = front + blocks[first:]

    blocks = walk_blocks(blocks, strip_wrappers)
    counter = [0]
    blocks = replace_images(blocks, counter)
    if counter[0] != 7:
        sys.exit(f"convert.py: expected 7 figures, found {counter[0]}")

    patched, requirements = 0, []
    converted = []
    for block in blocks:
        if block["t"] == "Table":
            patched += apply_endorsed_patches(block)
            requirements += anchor_requirements(block)
            block = convert_table(block)
        converted.append(block)
    if patched != len(ENDORSED_PATCHES):
        sys.exit(f"convert.py: applied {patched} of {len(ENDORSED_PATCHES)} endorsed patches")

    files = split(converted)
    by_id, by_ref = build_targets(files)

    args.out.mkdir(parents=True, exist_ok=True)
    offset = 0
    outputs: dict[str, str] = {}
    for name, file_blocks in files.items():

        def retarget(xs: Nodes, here: str = name) -> Nodes:
            return retarget_links(xs, by_id, here)

        def xrefs(xs: Nodes, here: str = name) -> Nodes:
            return link_xrefs(xs, by_ref, here)

        file_blocks = walk_blocks(file_blocks, retarget)
        file_blocks = walk_blocks(file_blocks, xrefs, headers=False)
        # Caption anchors go in after linking, so a caption's own label is never linked.
        anchored = []
        for block in file_blocks:
            anchor = caption_anchor(block)
            if anchor:
                block = {"t": "Para", "c": [raw_html(f'<a id="{anchor}"></a>'), *block["c"]]}
            anchored.append(block)
        markdown = write_markdown(anchored, api)
        if "<table" in markdown:
            sys.exit(f"convert.py: a table in {name} could not be set as a Markdown table")
        markdown, count = renumber_notes(markdown, offset)
        offset += count
        markdown = re.sub(
            r"^@@FIGURE-(\d+)@@$",
            lambda m: figure_markdown(int(m.group(1))),
            markdown,
            flags=re.MULTILINE,
        )
        outputs[name] = markdown

    index = (HERE / "index-header.md").read_text().rstrip()
    index = index + "\n\n" + outputs[INDEX_FILE].rstrip() + "\n\n" + contents(files) + "\n"
    outputs[INDEX_FILE] = index

    for name, markdown in outputs.items():
        (args.out / name).write_text(f"{GENERATED}\n\n{markdown.rstrip()}\n")
    print(
        f"wrote {len(outputs)} files to {args.out}: {offset} footnotes, "
        f"{counter[0]} figures, requirement anchors {', '.join(requirements)}"
    )


if __name__ == "__main__":
    main()
