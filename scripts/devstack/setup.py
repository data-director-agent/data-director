"""`dev.py setup`: ask for the settings, write each where it belongs, then install and build."""

from __future__ import annotations

import getpass
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from devstack import paths
from devstack.common import (
    EXAMPLE_PRINCIPAL,
    DevError,
    prepare_web,
    read_env,
    run,
    tool_problems,
    update_env,
)

KEYS_URL = "https://console.anthropic.com/settings/keys"
ORCID_ID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def mask(secret: str) -> str:
    """Enough of a key to recognise it, and no more."""
    return f"{secret[:3]}…{secret[-4:]}" if len(secret) > 12 else "…"


def principal_id(answer: str) -> str:
    """An ORCID iD as an IRI. A bare iD is given its prefix; another absolute IRI is kept."""
    answer = answer.strip()
    if ORCID_ID.match(answer):
        return f"https://orcid.org/{answer}"
    scheme = urlsplit(answer).scheme
    if (scheme in {"http", "https"} and urlsplit(answer).netloc) or scheme in {"urn", "mailto"}:
        return answer
    raise DevError("give an ORCID iD (0000-0002-1825-0097) or another absolute IRI")


@dataclass
class Prompter:
    """Asks the person questions. Tests give it scripted answers."""

    ask: Callable[[str], str] = input
    ask_secret: Callable[[str], str] = getpass.getpass
    accept_defaults: bool = False

    def text(self, question: str, default: str) -> str:
        if self.accept_defaults:
            return default
        return self.ask(f"{question} [{default}]: ").strip() or default

    def secret(self, question: str) -> str:
        return "" if self.accept_defaults else self.ask_secret(f"{question}: ").strip()

    def yes(self, question: str, default: bool) -> bool:
        if self.accept_defaults:
            return default
        answer = self.ask(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        return default if not answer else answer.startswith("y")


@dataclass
class Changes:
    written: list[Path] = field(default_factory=list)

    def note(self, path: Path) -> None:
        if path not in self.written:
            self.written.append(path)


def ask_principal(prompt: Prompter, changes: Changes) -> None:
    current = {**EXAMPLE_PRINCIPAL, **read_env(paths.ROOT_ENV)}
    print(
        "\nWhom runs act for. There is no sign-in yet, so every run is recorded as acting for this\n"
        "person (ADR-0018). Give your own name and ORCID iD, or press Enter to keep the value shown."
    )
    name = prompt.text("Your name", current["DD_PRINCIPAL_NAME"])
    while True:
        try:
            iri = principal_id(prompt.text("Your ORCID iD", current["DD_PRINCIPAL_ID"]))
            break
        except DevError as exc:
            if prompt.accept_defaults:
                raise
            print(f"  {exc}")
    update_env(
        paths.ROOT_ENV,
        {"DD_PRINCIPAL_NAME": name, "DD_PRINCIPAL_ID": iri},
        "# Written by `uv run scripts/dev.py setup`; read by `dev.py start` and Docker Compose.\n"
        "# Never put a model key here: every agent reads this file (ADR-0026).",
    )
    changes.note(paths.ROOT_ENV)


def ask_model_key(prompt: Prompter, changes: Changes) -> bool:
    """Ask for a model key and give it to the agents that use one. Whether one is set."""
    orchestrator = paths.AGENT_ENV_DIR / "orchestrator.env"
    current = read_env(orchestrator).get("ANTHROPIC_API_KEY", "")
    print(
        "\nAn Anthropic API key (optional). Without one, the home page talks to director.stub, a\n"
        "rule-based agent, and everything else works. With one, the model-backed orchestrator can\n"
        f"hold the conversation. Create a key at {KEYS_URL}. It is stored only in the files of\n"
        "the agents that use it (workbench/agents/), which git ignores."
    )
    shown = f"Enter keeps {mask(current)}" if current else "Enter skips"
    key = prompt.secret(f"Anthropic API key ({shown})") or current
    if not key:
        return False
    header = "# Written by `uv run scripts/dev.py setup`: this agent's own settings (ADR-0026)."
    if key != current:
        update_env(orchestrator, {"ANTHROPIC_API_KEY": key}, header)
        changes.note(orchestrator)
    if prompt.yes("Let the standards advisor use the model to explain its advice too?", False):
        standards = paths.AGENT_ENV_DIR / "standards.env"
        update_env(
            standards, {"DD_STANDARDS_EXPLAINER": "anthropic", "ANTHROPIC_API_KEY": key}, header
        )
        changes.note(standards)
    return True


def use_model_orchestrator(changes: Changes) -> None:
    """Name `orchestrator.model` in the local profile, raising its version (app/README.md)."""
    profile = paths.PROFILE
    text = (profile if profile.is_file() else paths.PROFILE_EXAMPLE).read_text(encoding="utf-8")
    if re.search(r"^orchestrator:\s*orchestrator\.model\s*$", text, re.MULTILINE):
        return
    text, named = re.subn(
        r"^orchestrator:.*$", "orchestrator: orchestrator.model", text, flags=re.M
    )
    version = re.search(r"^version:\s*(\d+)", text, re.MULTILINE)
    if not named or not version:
        raise DevError(
            f"{profile.relative_to(paths.ROOT)} has no `orchestrator` or `version` to change"
        )
    text = text.replace(version[0], f"version: {int(version[1]) + 1}", 1)
    profile.write_text(text, encoding="utf-8")
    changes.note(profile)


def setup(prompt: Prompter, install: bool = True) -> int:
    problems = tool_problems() if install else []
    for problem in problems:
        print(f"missing: {problem}")
    changes = Changes()
    ask_principal(prompt, changes)
    if ask_model_key(prompt, changes) and prompt.yes(
        "Make the model-backed orchestrator the one the home page talks to?", True
    ):
        use_model_orchestrator(changes)
    print("\nWrote " + ", ".join(str(p.relative_to(paths.ROOT)) for p in changes.written) + ".")
    if problems:
        print("Install what is missing above, then run setup again to install and build.")
        return 1
    if install:
        print()
        run(["uv", "sync", "--all-packages", "--all-extras"])
        prepare_web()
    print("\nReady. Start everything with:  uv run scripts/dev.py start")
    return 0
