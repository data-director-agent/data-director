"""`dd.py edit`: change `deployment.yaml` in an editor, check it before it is saved, then offer
to apply it.

The editor works on a copy in a private temporary directory, as sudoedit's does. The copy is
checked with the rules `apply` reads the file by (`deployment.parse`); a copy that breaks one is
offered back to the editor, and the file is only replaced by one that passes. Run as root through
sudo, the editor runs as the person who ran sudo, never as root.
"""

from __future__ import annotations

import os
import pwd
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from ddtool.common import Agent, DevError, load_agents, shown
from ddtool.deployment import Place, apply, parse, plan
from ddtool.setup import Prompter
from ddtool.vm import System, Vm

# Where the editor is named, in the order sudoedit reads them, and what runs when none is.
EDITOR_VARIABLES = ("SUDO_EDITOR", "VISUAL", "EDITOR")
FALLBACK_EDITORS = ("editor", "vi")
NEW_FILE_MODE = 0o644  # as deploy/install.sh makes it

Editor = Callable[[Path], int]


def editor_command(env: Mapping[str, str]) -> list[str]:
    """The editor to run, as a command to which the file is appended."""
    for name in EDITOR_VARIABLES:
        if command := shlex.split(env.get(name, "")):
            return command
    for name in FALLBACK_EDITORS:
        if shutil.which(name):
            return [name]
    raise DevError("no editor found: set EDITOR, such as EDITOR=nano")


def run_editor(path: Path) -> int:
    """Edit `path` and return the editor's exit status. As root through sudo, the file and its
    directory are handed to the person who ran sudo and the editor runs as them."""
    command = [*editor_command(os.environ), str(path)]
    sudo_uid = os.environ.get("SUDO_UID")
    if os.geteuid() != 0 or not sudo_uid:
        return subprocess.run(command, check=False).returncode
    person = pwd.getpwuid(int(sudo_uid))
    for owned in (path.parent, path):
        os.chown(owned, person.pw_uid, person.pw_gid)
    env = {**os.environ, "HOME": person.pw_dir, "USER": person.pw_name, "LOGNAME": person.pw_name}
    return subprocess.run(
        command,
        check=False,
        user=person.pw_uid,
        group=person.pw_gid,
        extra_groups=[],
        env=env,
        cwd=path.parent,
    ).returncode


def edit(
    system: System,
    place: Place,
    vm: Vm | None = None,
    *,
    editor: Editor = run_editor,
    prompt: Prompter | None = None,
    apply_now: bool | None = None,
) -> int:
    """Edit `place`'s deployment.yaml, save it if it is valid, and apply it if `apply_now` says
    so (None: ask). 0 when the instance is what the file says at the end."""
    if place.unit_dir is not None and not system.is_root():
        raise DevError("edit changes /etc/data-director: run it as root (sudo data-director edit)")
    prompt = prompt or Prompter()
    before = _starting_text(place)
    agents = load_agents(place.source / "app" / "config" / "agents.yaml")
    workdir = Path(tempfile.mkdtemp(prefix="data-director-edit-"))
    try:
        draft = workdir / place.deployment.name
        draft.write_text(before, encoding="utf-8")
        draft.chmod(0o600)
        after = _edited(draft, shown(place.deployment), agents, editor, prompt)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if after is None:
        print(f"Discarded the edit; nothing was saved to {shown(place.deployment)}.")
        return 1
    if place.deployment.is_file() and after == before:
        print(f"{shown(place.deployment)} is unchanged.")
    else:
        _save(place.deployment, after)
        print(f"saved {shown(place.deployment)}")
    return _follow_up(system, place, vm, prompt, apply_now=apply_now)


def _starting_text(place: Place) -> str:
    """The file as it stands, or the release's example when there is none yet."""
    if place.deployment.is_file():
        return place.deployment.read_text(encoding="utf-8")
    example = place.source / "config" / "examples" / "deployment.yaml"
    print(f"No {shown(place.deployment)} yet: starting from {shown(example)}.")
    return example.read_text(encoding="utf-8")


def _edited(
    draft: Path, label: str, agents: list[Agent], editor: Editor, prompt: Prompter
) -> str | None:
    """The draft's text once the editor leaves it valid, or None if the edit is given up."""
    while True:
        if editor(draft) != 0:
            print("The editor did not finish cleanly.")
            return None
        text = draft.read_text(encoding="utf-8")
        try:
            parse(text, label, agents)
        except DevError as exc:
            print(f"not saved: {exc}")
            if prompt.yes("Edit again?", default=True):
                continue
            return None
        return text


def _save(path: Path, text: str) -> None:
    """Replace `path` with `text` in one step, keeping its mode and owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    if path.exists():
        before = path.stat()
        tmp.chmod(before.st_mode & 0o777)
        if os.geteuid() == 0:
            os.chown(tmp, before.st_uid, before.st_gid)
    else:
        tmp.chmod(NEW_FILE_MODE)
    tmp.replace(path)


def _follow_up(
    system: System, place: Place, vm: Vm | None, prompt: Prompter, *, apply_now: bool | None
) -> int:
    """Say what `apply` would change, then apply it as `apply_now` says, or as the person
    answers."""
    _, planned = plan(system, place, vm)
    if planned.refusals:
        for refusal in planned.refusals:
            print(f"apply refuses: {refusal}")
        return 1
    pending = planned.pending(system)
    if not pending:
        print("Nothing to change.")
        return 0
    for item in pending:
        print(f"would change: {item}")
    if apply_now is None:
        apply_now = prompt.yes("Apply now?", default=True)
    if not apply_now:
        tool = "sudo data-director" if place.unit_dir is not None else "uv run scripts/dd.py"
        print(f"Not applied. Run `{tool} apply` when ready.")
        return 0
    return apply(system, place, vm)
