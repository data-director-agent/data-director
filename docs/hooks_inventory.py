"""An MkDocs hook that writes the guide's steps for making an inventory from the file the app reads.

`inventory/browser/src/making.json` says how to make an inventory on each operating system. The
app's **Make an inventory** dialog shows it (`@data-director/inventory`), and this hook puts the
same text in the guide where a page has a marker, so that the two never drift apart:

- `<!-- making-an-inventory:summary -->` becomes the one-sentence summary;
- `<!-- making-an-inventory:steps -->` becomes a section per operating system, each with its
  numbered steps and commands.

A file that cannot be read, or lacks a field, fails the build rather than leave a gap in the guide.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mkdocs.exceptions import PluginError

if TYPE_CHECKING:
    from mkdocs.livereload import LiveReloadServer

SOURCE = Path(__file__).resolve().parent.parent / "inventory/browser/src/making.json"
SUMMARY = "<!-- making-an-inventory:summary -->"
STEPS = "<!-- making-an-inventory:steps -->"


def _code(command: str, shell: str) -> str:
    return f"```{shell}\n{command}\n```"


def render_steps(making: dict[str, Any]) -> str:
    """The steps as Markdown: a level-three heading per system, then a numbered list."""
    steps = making["steps"]
    sections = []
    for system in making["systems"]:
        shell = "powershell" if system["id"] == "windows" else "sh"
        install = steps["install"].replace("uv", f"[uv]({making['uvGuide']})", 1)
        sections.append(
            "\n".join(
                [
                    f"### {system['name']}",
                    "",
                    f"1. {system['terminal']}",
                    f"2. {install}",
                    "",
                    _indent(_code(system["install"], shell)),
                    "",
                    f"3. {steps['run']}",
                    "",
                    _indent(_code(system["run"], shell)),
                ]
            )
        )
    sections.append(steps["after"])
    return "\n\n".join(sections)


def _indent(block: str) -> str:
    return "\n".join(f"    {line}" for line in block.splitlines())


def render(markdown: str, making: dict[str, Any]) -> str:
    """`markdown` with each marker replaced by the text it stands for."""
    return markdown.replace(SUMMARY, making["summary"]).replace(STEPS, render_steps(making))


def on_page_markdown(markdown: str, **_: object) -> str:
    if SUMMARY not in markdown and STEPS not in markdown:
        return markdown
    try:
        making = json.loads(SOURCE.read_text(encoding="utf-8"))
        return render(markdown, making)
    except (OSError, ValueError, KeyError) as e:
        raise PluginError(f"{SOURCE} could not be rendered into the user guide: {e!r}") from e


def on_serve(server: LiveReloadServer, **_: object) -> LiveReloadServer:
    server.watch(str(SOURCE))
    return server
