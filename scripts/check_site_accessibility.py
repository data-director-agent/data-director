"""Check every page of the built documentation site against WCAG 2.2 AA.

Each page in the site's sitemap, and its 404 page, is loaded in Chromium and checked by axe-core
with the same rule tags as the app shell's browser tests (app/web/e2e), then checked for reflow:
at 320 CSS pixels wide, the 400% zoom equivalent of WCAG 1.4.10, the page must not scroll
sideways. Both happen in each of the site's colour schemes, light (`default`) and dark (`slate`),
which the theme picks from the browser's preferred scheme. The site is served from its own directory under the path in its `site_url`, because
the 404 page links its styles and scripts by absolute path.

Each page is checked once its own document has loaded. Resources from outside the site (fonts,
badges, Mermaid) are waited for up to 10 s, so that a slow third party cannot fail the check;
a page whose outside resources had not loaded by then is still checked, and the report says so.

    uv run --locked --only-group docs mkdocs build --strict
    uv run --locked --only-group docs --only-group accessibility \\
        scripts/check_site_accessibility.py site

The browser comes from `playwright install chromium`. Exits 1 if any page has a violation, and
2 if the site cannot be read.
"""

from __future__ import annotations

import argparse
import functools
import sys
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, ViewportSize, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# The same tags as app/web/e2e/shell.spec.ts: WCAG 2.0, 2.1 and 2.2, levels A and AA.
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
# WCAG 1.4.10 Reflow: 320 CSS pixels is 1280 at 400% zoom.
REFLOW_WIDTH = 320
# Each of the theme's schemes (mkdocs.yml palette), with the browser preference that selects it.
SCHEMES = {"default": "light", "slate": "dark"}
DESKTOP: ViewportSize = {"width": 1280, "height": 800}
# How long a page's resources from outside the site are waited for, in milliseconds.
OUTSIDE_WAIT_MS = 10_000
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@dataclass
class Findings:
    """What failed, by axe rule, and which pages scroll sideways at the reflow width. `unsettled`
    holds the pages checked before their outside resources had loaded: a note, not a failure."""

    rules: dict[str, dict[str, object]] = field(default_factory=dict)
    pages: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    nodes: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    overflow: dict[str, int] = field(default_factory=dict)
    unsettled: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.rules or self.overflow)


def read_pages(site: Path) -> tuple[str, list[str]]:
    """The path the site is served under, and each page's path below it, from the sitemap."""
    sitemap = site / "sitemap.xml"
    try:
        locs = [
            loc.text or ""
            for loc in ET.parse(sitemap).getroot().iterfind("s:url/s:loc", SITEMAP_NS)
        ]
    except (OSError, ET.ParseError) as exc:
        raise SystemExit(f"cannot read {sitemap}: {exc}; build the site first") from None
    if not locs:
        raise SystemExit(f"{sitemap} lists no pages")
    paths = [urlsplit(loc).path for loc in locs]
    # The shortest path is the home page, whose path is the prefix of every other.
    prefix = min(paths, key=len)
    if not prefix.endswith("/") or not all(p.startswith(prefix) for p in paths):
        raise SystemExit(f"the pages in {sitemap} do not share the home page's path {prefix!r}")
    pages = [p[len(prefix) :] for p in paths]
    if (site / "404.html").is_file():
        pages.append("404.html")
    return prefix, pages


class SiteHandler(SimpleHTTPRequestHandler):
    """Serves the site's directory under its `site_url` path, and nothing else."""

    def __init__(self, *args: object, prefix: str, **kwargs: object) -> None:
        self.prefix = prefix
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def translate_path(self, path: str) -> str:
        if not path.startswith(self.prefix):
            return str(Path(self.directory) / "404.html")
        return super().translate_path("/" + path[len(self.prefix) :])

    def log_message(self, format: str, *args: object) -> None:
        pass


def serve(site: Path, prefix: str) -> ThreadingHTTPServer:
    handler = functools.partial(SiteHandler, directory=str(site), prefix=prefix)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def overflow(page: Page) -> int:
    """How far the page scrolls sideways, in CSS pixels."""
    width: int = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    return width


def check(base: str, pages: list[str]) -> Findings:
    """Every page in each scheme. A page is named `path (scheme)` where it is reported."""
    findings = Findings()
    axe = Axe()
    options = {"runOnly": {"type": "tag", "values": WCAG_TAGS}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for scheme, preference in SCHEMES.items():
            page = browser.new_page(viewport=DESKTOP, color_scheme=preference)
            for path in pages:
                name = f"{path} ({scheme})"
                response = page.goto(base + path, wait_until="domcontentloaded")
                if response is None or (response.status >= 400 and path != "404.html"):
                    raise SystemExit(f"{name}: the server answered {response and response.status}")
                try:
                    page.wait_for_load_state("load", timeout=OUTSIDE_WAIT_MS)
                except PlaywrightTimeoutError:
                    findings.unsettled.add(name)
                # A palette that does not follow the preference would check one scheme twice.
                applied = page.evaluate("document.body.getAttribute('data-md-color-scheme')")
                if applied != scheme:
                    raise SystemExit(f"{name}: the page is in the {applied!r} scheme")
                for violation in axe.run(page, options=options).response["violations"]:
                    rule = violation["id"]
                    findings.rules[rule] = violation
                    findings.pages[rule].add(name)
                    findings.nodes[rule] += len(violation["nodes"])
                page.set_viewport_size({"width": REFLOW_WIDTH, "height": DESKTOP["height"]})
                if (scroll := overflow(page)) > 0:
                    findings.overflow[name] = scroll
                page.set_viewport_size(DESKTOP)
            page.close()
        browser.close()
    return findings


def report(findings: Findings, checked: int) -> str:
    """The findings as Markdown, for the terminal and the job summary."""
    lines = ["## Accessibility of the documentation site", ""]
    if findings.unsettled:
        lines += [
            f"{len(findings.unsettled)} page(s) were checked before resources from outside the "
            f"site had loaded, after {OUTSIDE_WAIT_MS // 1000} s: "
            + ", ".join(f"`{p or '/'}`" for p in sorted(findings.unsettled)),
            "",
        ]
    if not findings:
        lines.append(
            f"{checked} pages checked in each scheme ({', '.join(SCHEMES)}) against WCAG 2.2 AA "
            f"(axe-core) and reflow at {REFLOW_WIDTH} CSS pixels: no violations."
        )
        return "\n".join(lines) + "\n"
    lines += [
        f"{checked} pages checked in each scheme ({', '.join(SCHEMES)}). "
        "Violations of WCAG 2.2 AA:",
        "",
    ]
    if findings.rules:
        lines += [
            "| Rule | Impact | Nodes | Pages | Example page | Example element |",
            "|---|---|---|---|---|---|",
        ]
        for rule, violation in sorted(findings.rules.items()):
            example = sorted(findings.pages[rule])[0]
            nodes = violation["nodes"]
            target = nodes[0]["target"] if isinstance(nodes, list) and nodes else ""
            lines.append(
                f"| [{rule}]({violation['helpUrl']}) | {violation['impact']} "
                f"| {findings.nodes[rule]} | {len(findings.pages[rule])} | `{example}` | `{target}` |"
            )
        lines.append("")
        for rule, violation in sorted(findings.rules.items()):
            lines.append(f"- **{rule}**: {violation['help']}")
        lines.append("")
    if findings.overflow:
        lines += [f"Pages that scroll sideways at {REFLOW_WIDTH} CSS pixels (WCAG 1.4.10):", ""]
        lines += [f"- `{path}`: {scroll} px" for path, scroll in sorted(findings.overflow.items())]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site", type=Path, help="the built site's directory (mkdocs.yml site_dir)")
    parser.add_argument("--summary", type=Path, help="append the report to this file as well")
    args = parser.parse_args(argv)
    site = args.site.resolve()
    try:
        prefix, pages = read_pages(site)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    server = serve(site, prefix)
    try:
        findings = check(f"http://127.0.0.1:{server.server_port}{prefix}", pages)
    finally:
        server.shutdown()
    text = report(findings, len(pages))
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as summary:
            summary.write(text)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
