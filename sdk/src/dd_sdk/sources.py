"""Sources built outside git, declared by the agents that cite them, and the one command that
prepares them all (docs/specs/grounding.md).

Some copies of a source are too large to commit, or may not be redistributed, so an agent pins
what they are built from and builds them where they are used. Each such copy is a `BuiltSource`
that its agent package registers under the entry-point group `dd.sources`:

    [project.entry-points."dd.sources"]
    re3data = "dd_agent_advisor_repository.registry:SOURCE"

`dd-sources prepare` then builds every registered source that is not built as pinned. Setup,
`start`, Docker Compose, CI and deployment all run that one command, so none of them, and not the
harness, needs to know how any agent builds its sources.

The entry-point name and `BuiltSource.name` are the same; it names the source's subdirectory of a
shared `--cache-dir`, where a source keeps what it downloads, so that it is downloaded once per pin
on each machine.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

GROUP = "dd.sources"
PREPARE_COMMAND = "uv run dd-sources prepare"


class SourceBuildError(Exception):
    """A source cannot be found, built or checked. The message says what to do."""


@dataclass(frozen=True)
class BuiltSource:
    """A copy of a source that its agent builds from something pinned.

    - `pin`: what the copy is built from, as a short stable string (an archive's SHA-256, say).
      Two machines with the same pins can share a cache.
    - `problem`: why the copy is not built as pinned, or None when it is.
    - `prepare`: build the copy, keeping downloads in `cache_dir`, or in the source's own default
      cache when that is None. Raises `SourceBuildError` when it cannot.
    """

    name: str
    pin: Callable[[], str]
    problem: Callable[[], str | None]
    prepare: Callable[[Path | None], None]


def discover() -> list[BuiltSource]:
    """Every built source the installed packages register, sorted by name."""
    found: dict[str, BuiltSource] = {}
    for point in entry_points(group=GROUP):
        where = point.dist.name if point.dist else point.value
        try:
            source = point.load()
        # Whatever an agent's module raises on import is reported as that agent's.
        except Exception as exc:  # noqa: BLE001
            raise SourceBuildError(
                f"{where}: cannot load built source {point.name!r}: {exc}"
            ) from None
        if not isinstance(source, BuiltSource):
            raise SourceBuildError(f"{where}: {point.value} is not a dd_sdk.sources.BuiltSource")
        if source.name != point.name:
            raise SourceBuildError(
                f"{where}: entry point {point.name!r} names a source called {source.name!r}"
            )
        if source.name in found:
            raise SourceBuildError(f"{where}: built source {source.name!r} is registered twice")
        found[source.name] = source
    return [found[name] for name in sorted(found)]


def _select(sources: list[BuiltSource], only: Sequence[str]) -> list[BuiltSource]:
    if unknown := sorted(set(only) - {s.name for s in sources}):
        known = ", ".join(s.name for s in sources) or "none"
        raise SourceBuildError(f"no built source called {', '.join(unknown)} (installed: {known})")
    return [s for s in sources if not only or s.name in only]


def prepare(
    sources: list[BuiltSource], cache_dir: Path | None = None, only: Sequence[str] = ()
) -> list[str]:
    """Build each source not built as pinned; return the names built."""
    built = []
    for source in _select(sources, only):
        if source.problem() is None:
            continue
        source.prepare(cache_dir / source.name if cache_dir else None)
        if (left := source.problem()) is not None:
            raise SourceBuildError(
                f"{source.name}: still not built as pinned after preparing: {left}"
            )
        built.append(source.name)
    return built


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-sources`."""
    parser = argparse.ArgumentParser(
        prog="dd-sources", description="Prepare the sources that agents build outside git."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="build every source not built as pinned")
    p.add_argument(
        "--cache-dir",
        type=Path,
        help="keep each source's downloads in a subdirectory of this (default: each source's own)",
    )
    p.add_argument("--only", action="append", default=[], metavar="NAME", help="this source only")
    sub.add_parser("check", help="exit 1 unless every source is built as pinned")
    sub.add_parser("pins", help="print each source's name and pin, for a cache key")
    args = parser.parse_args(argv)
    try:
        sources = discover()
        if args.command == "pins":
            sys.stdout.write("".join(f"{s.name} {s.pin()}\n" for s in sources))
            return 0
        if args.command == "check":
            problems = [(s.name, found) for s in sources if (found := s.problem()) is not None]
            for name, found in problems:
                sys.stdout.write(f"{name}: {found}\n")
            if not problems:
                sys.stdout.write(f"{len(sources)} built source(s) match their pins\n")
            return 1 if problems else 0
        built = prepare(sources, args.cache_dir, args.only)
    except SourceBuildError as exc:
        sys.stderr.write(f"dd-sources: {exc}\n")
        return 1
    current = len(_select(sources, args.only)) - len(built)
    sys.stdout.write(f"built: {', '.join(built) or 'none'}; already current: {current}\n")
    return 0
