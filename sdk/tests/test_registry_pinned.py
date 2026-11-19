"""dd_sdk.registry.pinned: the steps every registry built from a pinned archive repeats."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from dd_sdk.registry import pinned


class FixtureError(pinned.PinError):
    pass


@dataclass(frozen=True)
class Pin:
    archive: str
    archive_sha256: str
    snapshot_sha256: str
    extra: str = "x"


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "a")
    return buf.getvalue()


ARCHIVE = _zip()
URL = "https://example.org/export.zip"
PAUSED: list[float] = []
DOWNLOADER = pinned.Downloader("test/0", 5.0, FixtureError, sleep=PAUSED.append)


def _answering(*answers: int | Exception) -> tuple[httpx.Client, list[httpx.Request]]:
    """A client whose server gives each answer in turn: a status, or a transport error raised."""
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        answer = answers[len(seen)]
        seen.append(request)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, content=ARCHIVE if answer == 200 else b"")

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


def _serving(body: bytes, status: int = 200) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


def test_a_pin_round_trips(tmp_path: Path) -> None:
    pin = Pin("u", "a", "s")
    pinned.write_pin(pin, tmp_path / "manifest.json")
    assert pinned.read_pin(Pin, tmp_path / "manifest.json", "test", FixtureError) == pin


def test_an_unreadable_pin_raises_the_agents_error(tmp_path: Path) -> None:
    with pytest.raises(FixtureError):
        pinned.read_pin(Pin, tmp_path / "missing.json", "test", FixtureError)
    (tmp_path / "bad.json").write_text('{"nope": 1}', encoding="utf-8")
    with pytest.raises(FixtureError):
        pinned.read_pin(Pin, tmp_path / "bad.json", "test", FixtureError)


def test_same_pin_ignores_everything_but_the_hashes_and_archive() -> None:
    assert pinned.same_pin(Pin("u", "a", "s", extra="1"), Pin("u", "a", "s", extra="2"))
    assert not pinned.same_pin(Pin("u", "a", "s"), Pin("u", "a", "t"))
    assert not pinned.same_pin(None, Pin("u", "a", "s"))


def test_problem_is_none_only_for_the_pinned_bytes(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    digest = hashlib.sha256(b"x\n").hexdigest()
    assert pinned.problem(registry, digest, "test", "the pin") is not None
    registry.write_bytes(b"y\n")
    assert pinned.problem(registry, digest, "test", "the pin") is not None
    registry.write_bytes(b"x\n")
    assert pinned.problem(registry, digest, "test", "the pin") is None
    assert pinned.sha256_file(registry) == digest


def test_an_archive_is_downloaded_once_per_pin(tmp_path: Path) -> None:
    client, seen = _serving(ARCHIVE)
    sha = hashlib.sha256(ARCHIVE).hexdigest()
    path = tmp_path / "cache" / "export.zip"
    assert DOWNLOADER.archive(URL, sha, path, client) == path
    assert DOWNLOADER.archive(URL, sha, path, client) == path
    assert len(seen) == 1
    assert seen[0].url == URL
    assert not path.with_suffix(".part").exists()


def test_an_archive_that_does_not_match_its_pin_is_refused(tmp_path: Path) -> None:
    client, _ = _serving(ARCHIVE)
    with pytest.raises(FixtureError):
        DOWNLOADER.archive(URL, "0" * 64, tmp_path / "export.zip", client)


def test_an_unpinned_cached_file_that_is_not_a_zip_is_fetched_again(tmp_path: Path) -> None:
    path = tmp_path / "export.zip"
    path.write_bytes(b"<html>not yet published</html>")
    client, seen = _serving(ARCHIVE)
    DOWNLOADER.archive(URL, None, path, client)
    assert len(seen) == 1
    assert zipfile.is_zipfile(path)


def test_a_failed_download_raises_the_agents_error(tmp_path: Path) -> None:
    client, _ = _serving(b"", status=404)
    with pytest.raises(FixtureError):
        DOWNLOADER.download(URL, tmp_path / "export.zip", client)
    assert not (tmp_path / "export.zip").exists()


@pytest.mark.parametrize(
    "failure", [502, 503, 429, httpx.ConnectError("refused"), httpx.ReadTimeout("slow")]
)
def test_a_download_the_server_fails_is_tried_again(
    tmp_path: Path, failure: int | Exception
) -> None:
    PAUSED.clear()
    client, seen = _answering(failure, 200)
    DOWNLOADER.download(URL, tmp_path / "export.zip", client)
    assert (tmp_path / "export.zip").read_bytes() == ARCHIVE
    assert len(seen) == 2
    assert [DOWNLOADER.pauses[0]] == PAUSED
    assert not (tmp_path / "export.part").exists()


def test_a_server_that_keeps_failing_raises_after_every_pause(tmp_path: Path) -> None:
    PAUSED.clear()
    attempts = len(DOWNLOADER.pauses) + 1
    client, seen = _answering(*[503] * attempts)
    with pytest.raises(FixtureError, match="503"):
        DOWNLOADER.download(URL, tmp_path / "export.zip", client)
    assert len(seen) == attempts
    assert list(DOWNLOADER.pauses) == PAUSED
    assert not (tmp_path / "export.zip").exists()
    assert not (tmp_path / "export.part").exists()


def test_a_status_the_server_did_not_fail_is_not_tried_again(tmp_path: Path) -> None:
    PAUSED.clear()
    client, seen = _answering(404, 200)
    with pytest.raises(FixtureError, match="404"):
        DOWNLOADER.download(URL, tmp_path / "export.zip", client)
    assert len(seen) == 1
    assert PAUSED == []


def test_a_made_client_names_the_project(tmp_path: Path) -> None:
    client, own = DOWNLOADER.client(None)
    try:
        assert own
        assert client.headers["User-Agent"] == "test/0"
    finally:
        client.close()
    agent = pinned.user_agent("data-director-sdk", "data-director-sdk")
    assert agent.startswith("data-director-sdk/")
    assert pinned.PROJECT_URL in agent


def test_write_atomic_makes_the_directory(tmp_path: Path) -> None:
    target = tmp_path / "a" / "registry.jsonl"
    pinned.write_atomic(target, b"x\n")
    assert target.read_bytes() == b"x\n"


def test_check_exits_one_on_a_problem(capsys: pytest.CaptureFixture[str]) -> None:
    assert pinned.check(None, "fine") == 0
    assert pinned.check("broken", "fine") == 1
    assert capsys.readouterr().out.splitlines() == ["fine", "broken"]


def test_install_records_what_a_pin_needs(tmp_path: Path) -> None:
    archive = tmp_path / "export.zip"
    archive.write_bytes(ARCHIVE)
    built = pinned.install(tmp_path, b"a\nb\n", archive)
    assert built.records == 2
    assert built.archive_sha256 == hashlib.sha256(ARCHIVE).hexdigest()
    assert pinned.problem(built.path, built.snapshot_sha256, "test", "the pin") is None
