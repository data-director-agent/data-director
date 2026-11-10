"""`dd.py setup`: ask for the settings, write each where it belongs, then install and build."""

from __future__ import annotations

import getpass
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ddtool import paths
from ddtool.common import (
    EXAMPLE_PRINCIPAL,
    DevError,
    ensure_local_tree,
    prepare_sources,
    prepare_web,
    read_env,
    remove_env,
    run,
    shown,
    tool_problems,
    update_env,
)
from ddtool.deployment import Place, apply
from ddtool.secret import secret_file
from ddtool.vm import System

KEYS_URL = "https://console.anthropic.com/settings/keys"
FAIRSHARING_URL = "https://fairsharing.org/accounts/signup"
# The agents given the FAIRsharing login, and the setting that turns on their live search.
FAIRSHARING_AGENTS = (
    ("advisor-standards", "DD_STANDARDS_RETRIEVAL"),
    ("advisor-policy", "DD_POLICY_RETRIEVAL"),
)
# The database of Docker Compose's `postgres` profile (compose.yaml). Its locations name no host:
# libpq takes the host, the port and the password file from PGHOST, PGPORT and PGPASSFILE, which
# Compose sets for its containers and app.env for `dd.py start` (docs/specs/storage.md).
DB_USER = "dd"
DB_NAME = "dd"
DB_LOCATION = f"postgresql://{DB_USER}@/{DB_NAME}"
DB_PASSWORD = "postgres-password"  # read by the `db` service (POSTGRES_PASSWORD_FILE)
DB_PASSFILE = "pgpass"  # read by libpq in the app, the workbench and `db-migrate`
DB_HOST_PORT = "5432"  # compose.yaml's default DD_DB_HOST_PORT
STORAGE_VARS = ("DD_RUNS_DIR", "DD_PROJECTS_DIR")
DB_VARS = (*STORAGE_VARS, "PGHOST", "PGPORT", "PGPASSFILE")
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
        "person (docs/specs/policy-and-identity.md). Give your own name and ORCID iD, or press Enter to keep the value shown."
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
        "# Written by `uv run scripts/dd.py setup`; read by the app (`dd.py start`, Docker Compose).",
    )
    changes.note(paths.APP_ENV)


def key_file(agent: str) -> Path:
    return secret_file(agent, "anthropic-api-key")


def write_key(agent: str, key: str, changes: Changes, extra: dict[str, str] | None = None) -> None:
    """Store `key` as the agent's credential file, and name it in the agent's own settings."""
    path = key_file(agent)
    private_file(path, key + "\n", changes)
    env_file = paths.AGENT_ENV_DIR / f"{agent}.env"
    update_env(
        env_file,
        {"ANTHROPIC_API_KEY_FILE": path.name} | (extra or {}),
        "# Written by `uv run scripts/dd.py setup`: this agent's own settings (docs/specs/policy-and-identity.md).",
    )
    changes.note(env_file)


def read_key(agent: str) -> str:
    path = key_file(agent)
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def ask_model_key(prompt: Prompter, changes: Changes) -> bool:
    """Ask for a model key and give it to the agents that use one. Whether one is set."""
    current = read_key("orchestrator-model")
    print(
        "\nAn Anthropic API key (optional). Without one, the home page talks to orchestrator.stub, a\n"
        "rule-based agent, and everything else works. With one, the model-backed orchestrator can\n"
        f"hold the conversation. Create a key at {KEYS_URL}. It is stored only in the files of\n"
        "the agents that use it (config/local/credentials/), which git ignores."
    )
    shown = f"Enter keeps {mask(current)}" if current else "Enter skips"
    key = prompt.secret(f"Anthropic API key ({shown})") or current
    if not key:
        return False
    if key != current:
        write_key("orchestrator-model", key, changes)
    if prompt.yes("Let the standards advisor use the model to explain its advice too?", True):
        write_key("advisor-standards", key, changes, {"DD_STANDARDS_EXPLAINER": "anthropic"})
    return True


def ask_fairsharing(prompt: Prompter, changes: Changes) -> None:
    """Ask for a FAIRsharing account and give it to the agents that search FAIRsharing live."""
    current = read_env(paths.AGENT_ENV_DIR / "advisor-standards.env")
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
            "# Written by `uv run scripts/dd.py setup`: this agent's own settings (docs/specs/policy-and-identity.md).",
        )
        changes.note(own)


def private_file(path: Path, text: str, changes: Changes) -> None:
    """Write `text` to `path`, readable only by its owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(text, encoding="utf-8")
    changes.note(path)


def uses_postgres() -> bool:
    current = read_env(paths.APP_ENV)
    return any(current.get(var, "").startswith("postgresql://") for var in STORAGE_VARS)


def ask_postgres(prompt: Prompter, changes: Changes) -> None:
    """Ask whether to keep runs and projects in the `postgres` profile's database, and write its
    password and the app's locations if so; if not, put the app back on files."""
    print(
        "\nWhere runs and projects are kept. By default, in files (in volumes under Docker Compose).\n"
        "They can be kept in PostgreSQL instead, as a deployment with more than one instance does:\n"
        "Docker Compose runs it with `--profile postgres`, so nothing is installed on this machine."
    )
    if not prompt.yes("Keep runs and projects in PostgreSQL?", uses_postgres()):
        if remove_env(paths.APP_ENV, DB_VARS):
            changes.note(paths.APP_ENV)
            print("  Runs and projects are kept in files again; the database volume is kept.")
        return
    password_file = paths.CREDENTIALS_DIR / DB_PASSWORD
    # Never a new one: the database keeps the password it was first started with.
    password = password_file.read_text(encoding="utf-8").strip() if password_file.is_file() else ""
    if not password:
        password = secrets.token_urlsafe(32)
        private_file(password_file, password + "\n", changes)
    passfile = paths.CREDENTIALS_DIR / DB_PASSFILE
    # host:port:database:user:password, any host and port: `db` in Compose, localhost outside it.
    entry = f"*:*:{DB_NAME}:{DB_USER}:{password}\n"
    if not passfile.is_file() or passfile.read_text(encoding="utf-8") != entry:
        private_file(passfile, entry, changes)
    update_env(
        paths.APP_ENV,
        dict.fromkeys(STORAGE_VARS, DB_LOCATION)
        | {"PGHOST": "localhost", "PGPORT": DB_HOST_PORT, "PGPASSFILE": str(passfile)},
        "# Written by `uv run scripts/dd.py setup`; read by the app (`dd.py start`, Docker Compose).",
    )
    changes.note(paths.APP_ENV)
    print(
        "  Start it with:  docker compose --profile postgres up --build\n"
        "  or, for `dd.py start`:  docker compose --profile postgres up -d db db-migrate"
    )


def use_model_orchestrator(changes: Changes) -> None:
    """Name the model-backed orchestrator in `config/local/deployment.yaml`, which `apply` turns
    into the profile (scripts/ddtool/deployment.py)."""
    path = paths.LOCAL_DIR / "deployment.yaml"
    text = path.read_text(encoding="utf-8")
    changed, named = re.subn(r"^orchestrator:.*$", "orchestrator: model", text, flags=re.M)
    if not named:
        raise DevError(f"{shown(path)} has no `orchestrator` to change")
    if changed != text:
        path.write_text(changed, encoding="utf-8")
        changes.note(path)


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
    ask_postgres(prompt, changes)
    print("\nWrote " + ", ".join(str(p.relative_to(paths.ROOT)) for p in changes.written) + ".")
    print()
    if apply(System(), Place.dev()) != 0:
        return 1
    if problems:
        print("Install what is missing above, then run setup again to install and build.")
        return 1
    if install:
        print()
        run(["uv", "sync", "--all-packages", "--all-extras"])
        prepare_sources()
        prepare_web()
    print("\nReady. Start everything with:  uv run scripts/dd.py start")
    return 0
