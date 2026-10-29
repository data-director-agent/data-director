"""MkDocs hooks that publish the repository's own documents on the site, without copying them.

The guide (`docs/guide/`) is the site's `docs_dir`. Every other document stays where it is kept,
next to what it describes, and is mounted on the site at its repository path:

- A `nav` entry that starts with `/` names a file by its path from the repository root, as a
  GitHub link does. It may be a glob (`/docs/adr/*.md`), which expands in order to every match
  that the nav does not name elsewhere, each titled by its first heading.
- A link inside a published document is resolved against the document's place in the
  repository. One to another published document goes to its page; one to anything else (a YAML
  file, source code, a folder without a readme) goes to the file on GitHub, and one to nothing
  at all is reported, which fails `mkdocs build --strict`.
- A Markdown file that git tracks and that is neither published nor named in `UNPUBLISHED` is
  reported, so a new document does not go missing from the site.
"""

from __future__ import annotations

import fnmatch
import logging
import posixpath
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element

from markdown import Extension, Markdown
from markdown.treeprocessors import Treeprocessor
from markdown.util import AMP_SUBSTITUTE
from mkdocs.structure.files import File, Files

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.livereload import LiveReloadServer
    from mkdocs.structure.pages import Page

log = logging.getLogger("mkdocs.hooks.repository")

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"

# Tracked Markdown that is deliberately not on the site, with the reason.
UNPUBLISHED = (
    # An agent's system prompt is its code, read by the model rather than by people.
    "agents/*/src/*/system_prompt.md",
    # The licence of a third-party data snapshot, which travels with the data.
    "agents/standards/data/*",
    # The converter's input; the Blueprint's contents page (docs/blueprint/README.md) carries it.
    "scripts/blueprint/index-header.md",
)

# Where a document is mounted when its repository path cannot be its place on the site. The
# root readme would otherwise be taken for the home page.
MOUNTS = {"README.md": "repository.md"}

# Run with the Markdown renderer's link resolver (priority 0), and before it.
PRIORITY = 10

_mounted: dict[str, str] = {}  # repository path -> src_uri on the site
_repo_path: dict[str, str] = {}  # src_uri -> repository path, for every page
_src_uri: dict[str, str] = {}  # repository path -> src_uri, for every page
_current: list[str] = []  # repository path of the page being rendered


def _mount(path: str) -> str:
    return _mounted.setdefault(path, MOUNTS.get(path, path))


def _is_glob(entry: str) -> bool:
    return any(c in entry for c in "*?[")


def _entries(nav: list[Any]) -> list[str]:
    """Every repository path in the nav, at any depth."""
    out: list[str] = []
    for item in nav:
        value = next(iter(item.values())) if isinstance(item, dict) else item
        if isinstance(value, list):
            out.extend(_entries(value))
        elif isinstance(value, str) and value.startswith("/"):
            out.append(value.lstrip("/"))
    return out


def _expand(entry: str, named: set[str]) -> list[str]:
    pattern = entry.lstrip("/")
    if not _is_glob(pattern):
        if not (ROOT / pattern).is_file():
            log.warning("nav names %s, which is not in the repository", entry)
            return []
        return [_mount(pattern)]
    matches = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern) if p.is_file())
    if not matches:
        log.warning("nav names %s, which matches nothing in the repository", entry)
    return [_mount(m) for m in matches if m not in named]


def _walk(nav: list[Any], named: set[str]) -> list[Any]:
    out: list[Any] = []
    for item in nav:
        if isinstance(item, str) and item.startswith("/"):
            out.extend(_expand(item, named))
        elif isinstance(item, dict):
            ((title, value),) = item.items()
            if isinstance(value, list):
                out.append({title: _walk(value, named)})
            elif isinstance(value, str) and value.startswith("/"):
                out.extend({title: src} for src in _expand(value, named))
            else:
                out.append(item)
        else:
            out.append(item)
    return out


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    _mounted.clear()
    nav = config.nav or []
    # A glob leaves out what the nav names elsewhere, which can then have its own title or place.
    config.nav = _walk(nav, {e for e in _entries(nav) if not _is_glob(e)})
    config.markdown_extensions.append(_RepositoryLinks(config.repo_url or ""))
    return config


def on_files(files: Files, config: MkDocsConfig) -> Files:
    guide = Path(config.docs_dir).resolve().relative_to(ROOT).as_posix()
    _repo_path.clear()
    _src_uri.clear()
    for file in files:
        _repo_path[file.src_uri] = f"{guide}/{file.src_uri}"
        file.edit_uri = _repo_path[file.src_uri]
    for path, src_uri in _mounted.items():
        file = File.generated(config, src_uri, abs_src_path=str(ROOT / path))
        # The conformance report is generated by scripts/conformance_report.py.
        file.edit_uri = None if path == "CONFORMANCE.md" else path
        files.append(file)
        _repo_path[src_uri] = path
    _src_uri.update((repo, src) for src, repo in _repo_path.items())
    _report_unpublished()
    return files


def _report_unpublished() -> None:
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.split()
    except OSError, subprocess.CalledProcessError:
        log.info("git is not available, so unpublished documents are not reported")
        return
    published = set(_repo_path.values())
    for path in tracked:
        if path not in published and not any(fnmatch.fnmatch(path, p) for p in UNPUBLISHED):
            log.warning(
                "%s is not on the site: add it to the nav in mkdocs.yml, or to "
                "UNPUBLISHED in docs/hooks.py",
                path,
            )


def on_page_markdown(markdown: str, page: Page, **_: object) -> str:
    _current[:] = [_repo_path[page.file.src_uri]]
    return markdown


def on_serve(server: LiveReloadServer, **_: object) -> LiveReloadServer:
    for path in _mounted:
        server.watch(str(ROOT / path))
    return server


class _RepositoryLinks(Extension):
    def __init__(self, repo_url: str) -> None:
        super().__init__()
        self.repo_url = repo_url.rstrip("/")

    def extendMarkdown(self, md: Markdown) -> None:  # noqa: N802 (Markdown's API)
        md.treeprocessors.register(_Resolve(md, self.repo_url), "repository_links", PRIORITY)


class _Resolve(Treeprocessor):
    def __init__(self, md: Markdown, repo_url: str) -> None:
        super().__init__(md)
        self.repo_url = repo_url

    def run(self, root: Element) -> None:
        if not _current:
            return
        page = _current[0]
        for el in root.iter():
            attr = {"a": "href", "img": "src"}.get(el.tag)
            if attr and (url := el.get(attr)):
                el.set(attr, self.resolve(page, url))

    def resolve(self, page: str, url: str) -> str:
        # An e-mail address is obfuscated into entities, so has no scheme to recognise.
        if url.startswith(AMP_SUBSTITUTE):
            return url
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path:
            return url
        if parts.path.startswith("/"):
            target = posixpath.normpath(parts.path.lstrip("/"))
        else:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(page), parts.path))
        if target.startswith(".."):
            return url
        suffix = (f"?{parts.query}" if parts.query else "") + (
            f"#{parts.fragment}" if parts.fragment else ""
        )
        on_disk = ROOT / target
        if on_disk.is_dir():
            readme = posixpath.join(target, "README.md") if target != "." else "README.md"
            if readme not in _src_uri:
                return f"{self.repo_url}/tree/{BRANCH}/{target}{suffix}"
            target = readme
        if target in _src_uri:
            here = posixpath.dirname(_src_uri[page]) or "."
            return posixpath.relpath(_src_uri[target], here) + suffix
        if not on_disk.exists():
            log.warning("%s links to %s, which is not in the repository", page, url)
            return url
        return f"{self.repo_url}/blob/{BRANCH}/{target}{suffix}"
