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
    ensure_local_tree,
    prepare_web,
    read_env,
    run,
    tool_problems,
    update_env,
)

KEYS_URL = "https://console.anthropic.com/settings/keys"
FAIRSHARING_URL = "https://fairsharing.org/accounts/signup"
# The agents given the FAIRsharing login, and the setting that turns on their live search.
FAIRSHARING_AGENTS = (("standards", "DD_STANDARDS_RETRIEVAL"), ("policy", "DD_POLICY_RETRIEVAL"))
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
    current = EXAMPLE_PRINCIPAL | {k: v for k, v in read_env(paths.APP_ENV).items() if v}
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
        paths.APP_ENV,
        {"DD_PRINCIPAL_NAME": name, "DD_PRINCIPAL_ID": iri},
        "# Written by `uv run scripts/dev.py setup`; read by the app (`dev.py start`, Docker Compose).",
    )
    changes.note(paths.APP_ENV)


def key_file(agent: str) -> Path:
    return paths.CREDENTIALS_DIR / f"{agent}-anthropic-api-key"


def write_key(agent: str, key: str, changes: Changes, extra: dict[str, str] | None = None) -> None:
    """Store `key` as the agent's credential file, and name it in the agent's own settings."""
    path = key_file(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(key + "\n", encoding="utf-8")
    changes.note(path)
    env_file = paths.AGENT_ENV_DIR / f"{agent}.env"
    update_env(
        env_file,
        {"ANTHROPIC_API_KEY_FILE": path.name} | (extra or {}),
        "# Written by `uv run scripts/dev.py setup`: this agent's own settings (ADR-0026).",
    )
    changes.note(env_file)


def read_key(agent: str) -> str:
    path = key_file(agent)
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def ask_model_key(prompt: Prompter, changes: Changes) -> bool:
    """Ask for a model key and give it to the agents that use one. Whether one is set."""
    current = read_key("orchestrator")
    print(
        "\nAn Anthropic API key (optional). Without one, the home page talks to director.stub, a\n"
        "rule-based agent, and everything else works. With one, the model-backed orchestrator can\n"
        f"hold the conversation. Create a key at {KEYS_URL}. It is stored only in the files of\n"
        "the agents that use it (config/local/credentials/), which git ignores."
    )
    shown = f"Enter keeps {mask(current)}" if current else "Enter skips"
    key = prompt.secret(f"Anthropic API key ({shown})") or current
    if not key:
        return False
    if key != current:
        write_key("orchestrator", key, changes)
    if prompt.yes("Let the standards advisor use the model to explain its advice too?", False):
        write_key("standards", key, changes, {"DD_STANDARDS_EXPLAINER": "anthropic"})
    return True


def ask_fairsharing(prompt: Prompter, changes: Changes) -> None:
    """Ask for a FAIRsharing account and give it to the agents that search FAIRsharing live."""
    current = read_env(paths.AGENT_ENV_DIR / "standards.env")
    print(
        "\nA FAIRsharing account (optional). Without one, the standards and policy advisors search\n"
        f"their bundled snapshots. With one, they search FAIRsharing itself. Sign up at\n"
        f"{FAIRSHARING_URL}. FAIRsharing issues its token on sign-in, so the advisors take the\n"
        "login and password."
    )
    login = prompt.text("FAIRsharing login, Enter skips", current.get("FAIRSHARING_LOGIN", ""))
    if not login:
        return
    kept = current.get("FAIRSHARING_PASSWORD", "")
    shown = f"Enter keeps {mask(kept)}" if kept else "required"
    password = prompt.secret(f"FAIRsharing password ({shown})") or kept
    if not password:
        print("  No password given; FAIRsharing live search is not set up.")
        return
    for agent, switch in FAIRSHARING_AGENTS:
        own = paths.AGENT_ENV_DIR / f"{agent}.env"
        update_env(
            own,
            {switch: "live", "FAIRSHARING_LOGIN": login, "FAIRSHARING_PASSWORD": password},
            "# Written by `uv run scripts/dev.py setup`: this agent's own settings (ADR-0026).",
        )
        changes.note(own)


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
    for created in ensure_local_tree():
        changes.note(created)
    ask_principal(prompt, changes)
    if ask_model_key(prompt, changes) and prompt.yes(
        "Make the model-backed orchestrator the one the home page talks to?", True
    ):
        use_model_orchestrator(changes)
    ask_fairsharing(prompt, changes)
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
