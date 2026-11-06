"""`dd-sources`: every built source the installed agents declare, prepared by one command."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from dd_sdk import sources
from dd_sdk.sources import BuiltSource, SourceBuildError


class FakeSource:
    """A source that is built once `prepare` has run, recording the cache it was given."""

    def __init__(self, name: str, built: bool = False, builds: bool = True) -> None:
        self.name, self.built, self.builds = name, built, builds
        self.caches: list[Path | None] = []
        self.source = BuiltSource(
            name=name, pin=lambda: f"pin-{name}", problem=self.problem, prepare=self.prepare
        )

    def problem(self) -> str | None:
        return None if self.built else f"{self.name} is not built"

    def prepare(self, cache_dir: Path | None) -> None:
        self.caches.append(cache_dir)
        self.built = self.builds


def _register(monkeypatch: pytest.MonkeyPatch, **objects: object) -> None:
    """Install `objects` as the `dd.sources` entry points, by name."""
    module = "tests_fake_sources"
    points = [EntryPoint(name, f"{module}:{name}", sources.GROUP) for name in objects]
    fake = type(sources)(module)
    for name, obj in objects.items():
        setattr(fake, name, obj)
    monkeypatch.setitem(__import__("sys").modules, module, fake)
    monkeypatch.setattr(sources, "entry_points", lambda group: points)


def test_prepare_builds_each_unbuilt_source_in_its_own_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    b, a, c = FakeSource("b"), FakeSource("a"), FakeSource("c", built=True)
    _register(monkeypatch, b=b.source, a=a.source, c=c.source)
    assert sources.main(["prepare", "--cache-dir", str(tmp_path)]) == 0
    assert (a.caches, b.caches, c.caches) == ([tmp_path / "a"], [tmp_path / "b"], [])
    assert "built: a, b; already current: 1" in capsys.readouterr().out
    assert sources.main(["prepare"]) == 0  # all current: nothing is prepared again
    assert len(a.caches) == 1


def test_prepare_without_a_cache_dir_leaves_each_source_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = FakeSource("a")
    _register(monkeypatch, a=a.source)
    assert sources.main(["prepare", "--only", "a"]) == 0
    assert a.caches == [None]


def test_check_and_pins(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = FakeSource("a", built=True), FakeSource("b")
    _register(monkeypatch, b=b.source, a=a.source)
    assert sources.main(["pins"]) == 0
    assert capsys.readouterr().out == "a pin-a\nb pin-b\n"
    assert sources.main(["check"]) == 1
    assert capsys.readouterr().out == "b: b is not built\n"
    b.built = True
    assert sources.main(["check"]) == 0


@pytest.mark.parametrize(
    ("objects", "message"),
    [
        ({"a": object()}, "is not a dd_sdk.sources.BuiltSource"),
        ({"a": FakeSource("b").source}, "entry point 'a' names a source called 'b'"),
    ],
)
def test_a_wrong_declaration_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    objects: dict[str, object],
    message: str,
) -> None:
    _register(monkeypatch, **objects)
    assert sources.main(["check"]) == 1
    assert message in capsys.readouterr().err


def test_a_source_that_cannot_be_loaded_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    point = EntryPoint("a", "no_such_module_here:SOURCE", sources.GROUP)
    monkeypatch.setattr(sources, "entry_points", lambda group: [point])
    assert sources.main(["prepare"]) == 1
    assert "cannot load built source 'a'" in capsys.readouterr().err


def test_a_source_registered_twice_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    a = FakeSource("a")
    _register(monkeypatch, a=a.source)
    point = EntryPoint("a", "tests_fake_sources:a", sources.GROUP)
    monkeypatch.setattr(sources, "entry_points", lambda group: [point, point])
    with pytest.raises(SourceBuildError, match="registered twice"):
        sources.discover()


def test_a_failed_or_ineffective_prepare_fails_the_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(cache_dir: Path | None) -> None:
        raise SourceBuildError("a: the download does not match its pin")

    broken = BuiltSource("a", pin=lambda: "p", problem=lambda: "not built", prepare=refuse)
    _register(monkeypatch, a=broken)
    assert sources.main(["prepare"]) == 1
    assert "the download does not match its pin" in capsys.readouterr().err

    _register(monkeypatch, a=FakeSource("a", builds=False).source)
    assert sources.main(["prepare"]) == 1
    assert "not built as pinned after preparing" in capsys.readouterr().err


def test_only_names_an_installed_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _register(monkeypatch, a=FakeSource("a").source)
    assert sources.main(["prepare", "--only", "z"]) == 1
    assert "no built source called z (installed: a)" in capsys.readouterr().err
