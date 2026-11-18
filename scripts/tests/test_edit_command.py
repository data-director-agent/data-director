"""`dd.py edit` (scripts/ddtool/edit.py): deployment.yaml is changed in an editor, checked before
it is saved, and applied when asked."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import dd  # noqa: E402
from ddtool import paths  # noqa: E402
from ddtool.common import DevError, load_agents  # noqa: E402
from ddtool.deployment import Place, parse  # noqa: E402
from ddtool.edit import edit as run_edit  # noqa: E402
from ddtool.edit import editor_command  # noqa: E402
from ddtool.setup import Prompter  # noqa: E402
from ddtool.vm import System  # noqa: E402

STUB = "name: test\norchestrator: stub\n"
NO_HELLO = "name: test\norchestrator: stub\ndisabled: [example-hello]\n"


@pytest.fixture
def place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Place:
    """A development instance: a release with the app's agents and examples, and settings with
    the stub orchestrator applied."""
    source = tmp_path / "source"
    (source / "app" / "config").mkdir(parents=True)
    for name in ("agents.yaml", "profile.yaml.example"):
        shutil.copyfile(ROOT / "app" / "config" / name, source / "app" / "config" / name)
    shutil.copytree(ROOT / "config" / "examples", source / "config" / "examples")
    etc = tmp_path / "etc"
    monkeypatch.setattr(paths, "AGENT_ENV_DIR", etc / "agents")
    monkeypatch.setattr(paths, "CREDENTIALS_DIR", etc / "credentials")
    found = Place(etc, source)
    etc.mkdir()
    found.deployment.write_text(STUB)
    assert run_edit(System(), found, editor=writes(STUB), apply_now=True) == 0
    return found


def writes(*texts: str, status: int = 0, seen: list[str] | None = None) -> Callable[[Path], int]:
    """An editor that leaves each of `texts` in the file in turn, recording what it was given."""
    queue = list(texts)

    def editor(path: Path) -> int:
        if seen is not None:
            seen.append(path.read_text())
        if queue:
            path.write_text(queue.pop(0))
        return status

    return editor


def answers(*replies: str, asked: list[str] | None = None) -> Prompter:
    queue = list(replies)

    def ask(question: str) -> str:
        if asked is not None:
            asked.append(question)
        return queue.pop(0) if queue else ""

    return Prompter(ask=ask)


def profile(place: Place) -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(place.profile.read_text())
    return loaded


def test_a_valid_edit_is_saved_and_applied_when_the_answer_is_yes(place: Place) -> None:
    version = profile(place)["version"]
    status = run_edit(System(), place, editor=writes(NO_HELLO), prompt=answers("y"))
    assert status == 0
    assert place.deployment.read_text() == NO_HELLO
    applied = profile(place)
    assert "example.hello" not in dict(applied["agents"])  # type: ignore[call-overload]
    assert applied["version"] != version


def test_no_apply_saves_the_file_and_leaves_the_profile(place: Place) -> None:
    before = place.profile.read_text()
    asked: list[str] = []
    status = run_edit(
        System(), place, editor=writes(NO_HELLO), prompt=answers(asked=asked), apply_now=False
    )
    assert status == 0
    assert place.deployment.read_text() == NO_HELLO
    assert place.profile.read_text() == before
    assert not asked


def test_apply_asks_nothing(place: Place) -> None:
    asked: list[str] = []
    status = run_edit(
        System(), place, editor=writes(NO_HELLO), prompt=answers(asked=asked), apply_now=True
    )
    assert status == 0
    assert not asked
    assert "example.hello" not in dict(profile(place)["agents"])  # type: ignore[call-overload]


@pytest.mark.parametrize("bad", ["name: [unclosed\n", "name: test\ncolour: blue\n"])
def test_an_invalid_edit_is_not_saved_and_is_offered_back_with_the_edits(
    place: Place, bad: str
) -> None:
    seen: list[str] = []
    status = run_edit(
        System(), place, editor=writes(bad, NO_HELLO, seen=seen), prompt=answers("", "n")
    )
    assert status == 0
    assert seen == [STUB, bad]  # the second time, the editor has the broken copy back
    assert place.deployment.read_text() == NO_HELLO


def test_giving_up_on_an_invalid_edit_leaves_the_file(place: Place) -> None:
    status = run_edit(System(), place, editor=writes("orchestrator: both\n"), prompt=answers("n"))
    assert status == 1
    assert place.deployment.read_text() == STUB


def test_an_editor_that_fails_leaves_the_file(place: Place) -> None:
    status = run_edit(System(), place, editor=writes(NO_HELLO, status=1), apply_now=True)
    assert status == 1
    assert place.deployment.read_text() == STUB


def test_an_unchanged_file_is_not_rewritten(place: Place) -> None:
    mtime = place.deployment.stat().st_mtime_ns
    assert run_edit(System(), place, editor=writes(), apply_now=True) == 0
    assert place.deployment.stat().st_mtime_ns == mtime


def test_the_saved_file_keeps_its_mode(place: Place) -> None:
    place.deployment.chmod(0o600)
    run_edit(System(), place, editor=writes(NO_HELLO), apply_now=False)
    assert place.deployment.stat().st_mode & 0o777 == 0o600


def test_without_a_file_the_edit_starts_from_the_example(place: Place) -> None:
    place.deployment.unlink()
    seen: list[str] = []
    run_edit(System(), place, editor=writes(STUB, seen=seen), apply_now=False)
    example = place.source / "config" / "examples" / "deployment.yaml"
    assert seen == [example.read_text()]
    assert place.deployment.read_text() == STUB


def test_a_model_orchestrator_without_its_key_is_saved_but_not_applied(place: Place) -> None:
    before = place.profile.read_text()
    model = "name: test\norchestrator: model\n"
    status = run_edit(System(), place, editor=writes(model), apply_now=True)
    assert status == 1
    assert place.deployment.read_text() == model
    assert place.profile.read_text() == before


class NotRoot(System):
    def is_root(self) -> bool:
        return False


def test_on_a_vm_edit_needs_root(place: Place, tmp_path: Path) -> None:
    vm_place = Place(place.etc, place.source, tmp_path / "systemd")
    with pytest.raises(DevError):
        run_edit(NotRoot(), vm_place, editor=writes(NO_HELLO))
    assert place.deployment.read_text() == STUB


def test_problems_name_the_file_as_the_operator_knows_it() -> None:
    agents = load_agents(ROOT / "app" / "config" / "agents.yaml")
    with pytest.raises(DevError, match=r"^/etc/data-director/deployment\.yaml"):
        parse("colour: blue\n", "/etc/data-director/deployment.yaml", agents)


def test_the_editor_is_chosen_as_sudoedit_chooses_it() -> None:
    every = {"SUDO_EDITOR": "nano -w", "VISUAL": "code --wait", "EDITOR": "vim"}
    assert editor_command(every) == ["nano", "-w"]
    assert editor_command({**every, "SUDO_EDITOR": ""}) == ["code", "--wait"]
    assert editor_command({"EDITOR": "vim"}) == ["vim"]


def test_no_editor_anywhere_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ddtool.edit.shutil.which", lambda _name: None)
    with pytest.raises(DevError):
        editor_command({})


def test_apply_and_no_apply_cannot_both_be_given() -> None:
    with pytest.raises(SystemExit):
        dd._parser().parse_args(["edit", "--apply", "--no-apply"])
    assert dd._parser().parse_args(["edit"]).apply_now is None
    assert dd._parser().parse_args(["edit", "--no-apply"]).apply_now is False
