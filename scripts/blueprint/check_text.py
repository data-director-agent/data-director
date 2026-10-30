# /// script
# requires-python = ">=3.12"
# ///
"""Compare the words of docs/blueprint/ with the published Blueprint PDF.

Usage:
    uv run scripts/blueprint/check_text.py PDF [--dir docs/blueprint]

Requires pdftotext (poppler) and pandoc on PATH. Both texts are reduced to their words (runs of
letters and digits; numbers alone are dropped, since page numbers are numbers) and the two word
sequences are aligned. A footnote marker is glued to the word before it, as pdftotext prints it.

Footnotes sit at the foot of a page in the PDF and at the end of a file here, and pdftotext reads
some table cells in another order, so a word left over on one side of the alignment that is also
left over on the other counts as moved, not changed. Every other leftover word is printed with
its context; the exit status is 1 if any is not in ALLOWED.
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Running headers and footers printed on every page of the PDF.
PAGE_FURNITURE = (
    re.compile(r"^Data Director AI Agent - Open Technology-Agnostic Blueprint$"),
    re.compile(r"^v1\.0$"),
    re.compile(r"^RDA-Microsoft Global Agentic AI Initiative \| Blueprint open for community"),
    re.compile(r"^Page \d+$"),
)
WORD = re.compile(r"[^\W_]+")

# Leftover words that are expected: (side, word) -> count.
ALLOWED = Counter(
    {
        # This edition's title for the index page; the PDF's cover has the title in other words.
        ("markdown", "Data"): 1,
        ("markdown", "Director"): 1,
        ("markdown", "Agentic"): 1,
        ("markdown", "AI"): 1,
        ("markdown", "Tool"): 1,
        ("markdown", "Blueprint"): 1,
        # "14. Appendices" has no text of its own; the index lists the appendices under it.
        ("pdf", "Appendices"): 1,
        # Header rows the PDF repeats at the top of a continued page: Table 4 once ("Rationale")
        # and Table 10 twice.
        ("pdf", "Rationale"): 3,
        ("pdf", "No"): 3,
        ("pdf", "Commenter"): 3,
        ("pdf", "Comment"): 3,
        ("pdf", "Summary"): 3,
        ("pdf", "Disposition"): 3,
        ("pdf", "Section"): 3,
        # A word split inside a table cell in the PDF ("recommendati on", Table 3, R2).
        ("markdown", "recommendation"): 1,
        ("pdf", "recommendati"): 1,
        ("pdf", "on"): 1,
    }
)


def run(command: list[str], stdin: str | None = None) -> str:
    try:
        return subprocess.run(
            command, input=stdin, capture_output=True, text=True, check=True
        ).stdout
    except FileNotFoundError:
        sys.exit(f"check_text.py: {command[0]} is not on PATH")
    except subprocess.CalledProcessError as error:
        sys.exit(f"check_text.py: {command[0]} failed:\n{error.stderr}")


def words(text: str) -> list[str]:
    # pdftotext joins a word hyphenated across a line ("machine-\nreadable" becomes
    # "machinereadable"), so hyphens are dropped on both sides.
    text = re.sub(r"(?<=\w)-(?=\w)", "", text)
    return [w for w in WORD.findall(text) if not w.isdigit()]


def pdf_words(pdf: Path) -> list[str]:
    text = run(["pdftotext", str(pdf), "-"])
    # The table of contents; the edition generates its own from the headings.
    start, end = text.index("Table of Contents"), text.index("Document Control")
    text = text[:start] + text[end:]
    kept = [
        line
        for line in text.splitlines()
        if not any(p.search(line.strip()) for p in PAGE_FURNITURE)
    ]
    return words("\n".join(kept))


def markdown_words(directory: Path) -> list[str]:
    names = sorted(p.name for p in directory.glob("*.md"))
    # The index, the chapters (01-… to 13-…), then the appendices.
    order = (
        ["README.md"]
        + [n for n in names if n[0].isdigit()]
        + [n for n in names if n.startswith("appendix-")]
    )
    out: list[str] = []
    for name in order:
        source = (directory / name).read_text()
        source = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)
        source = re.sub(r"```mermaid\n.*?```", "", source, flags=re.DOTALL)
        source = source.replace("<br>", " ")
        # Footnote markers as pdftotext prints them, glued to the word before.
        source = re.sub(r"^\[\^\d+\]: ", "", source, flags=re.MULTILINE)
        source = re.sub(r"\[\^(\d+)\]", r"\1", source)
        if name == "README.md":
            # This edition's notice, and the generated contents list.
            source = re.sub(r"^> \[!NOTE\]\n(?:>.*\n)+", "", source, flags=re.MULTILINE)
            source = source.split("\n## Contents\n")[0]
        out += words(run(["pandoc", "-f", "gfm", "-t", "plain", "--wrap=none"], source))
    return out


def leftovers(ours: list[str], theirs: list[str]) -> list[tuple[str, str, str]]:
    """Words neither aligned nor moved, as (side, word, context)."""
    matcher = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    spans: list[tuple[str, list[str], int, int]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op != "equal":
            spans += [("markdown", ours, i1, i2), ("pdf", theirs, j1, j2)]
    counts: dict[str, Counter[str]] = {"markdown": Counter(), "pdf": Counter()}
    for side, seq, start, stop in spans:
        counts[side].update(seq[start:stop])
    moved = counts["markdown"] & counts["pdf"]
    remaining = {side: counts[side] - moved for side in counts}
    found = []
    for side, seq, start, stop in spans:
        for k in range(start, stop):
            if remaining[side][seq[k]] > 0:
                remaining[side][seq[k]] -= 1
                found.append((side, seq[k], " ".join(seq[max(0, k - 6) : k + 7])))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--dir", type=Path, default=Path("docs/blueprint"))
    args = parser.parse_args()

    ours, theirs = markdown_words(args.dir), pdf_words(args.pdf)
    found = leftovers(ours, theirs)
    allowed = ALLOWED.copy()
    unexpected = []
    for side, word, context in found:
        if allowed[(side, word)] > 0:
            allowed[(side, word)] -= 1
        else:
            unexpected.append((side, word, context))
    for side, word, context in unexpected:
        print(f"only in the {side}: {word!r} in: {context}")
    unused = +allowed
    for (side, word), count in unused.items():
        print(f"allowed but not found: {count} x {word!r} only in the {side}")
    print(
        f"{len(ours)} words in the Markdown, {len(theirs)} in the PDF; "
        f"{len(found) - len(unexpected)} allowed and {len(unexpected)} unexpected leftover words"
    )
    sys.exit(1 if unexpected or unused else 0)


if __name__ == "__main__":
    main()
