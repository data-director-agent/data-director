"""`dd.py doctor` on a VM: check the deployment, its services, its secrets and the live app, and
name the command that fixes each problem. It changes nothing.

Run as root to check everything: the settings files and secrets are root's. As another user it
checks what that user can read and says what it skipped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ddtool.common import (
    KEY_VARS,
    MODEL_BACKED,
    Agent,
    DevError,
    compare_profile,
    load_agents,
)
from ddtool.deployment import Place, plan
from ddtool.vm import (
    System,
    Vm,
    about,
    agent_instances,
    agent_unit,
    domain,
    is_active,
    loaded_secrets,
    read_settings,
    systemctl_show,
    wanted_agents,
)

APP_UNIT = "data-director-app.service"
DEPLOY_UNIT = "data-director-deploy.service"
ADMIN_UNIT = "data-director-admin.service"
# The settings the app needs to sign people in (deploy/install.sh waits for them).
SIGN_IN_SETTINGS = ("DD_OIDC_ISSUER", "DD_OIDC_CLIENT_ID", "DD_APP_PUBLIC_URL")
OPERATOR_SETTINGS = ("DD_PRINCIPAL_ID", "DD_PRINCIPAL_NAME")
MODEL_KEY = "anthropic-api-key"
BACKUP_UNIT = "data-director-backup.service"
BACKUP_TIMER = "data-director-backup.timer"
# A backup older than this means the nightly one has stopped (deploy/README.md, "Backups").
BACKUP_MAX_AGE = timedelta(days=2)
BACKUP_NAME = re.compile(r"^\d{8}T\d{6}Z$")
# Less free than this share of a file system, and a store or a backup may soon not fit.
LOW_DISK = 0.10
# The settings that name a store, by the file that holds them.
STORE_SETTINGS = (
    ("app_env", "DD_RUNS_DIR"),
    ("app_env", "DD_PROJECTS_DIR"),
    ("workbench_env", "DD_RUNS_DIR"),
)


@dataclass
class Report:
    """What doctor found: problems (each with its fix), notes, and checks it could not make."""

    problems: list[tuple[str, str | None]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def problem(self, text: str, fix: str | None = None) -> None:
        self.problems.append((text, fix))

    def note(self, text: str) -> None:
        self.notes.append(text)

    def skip(self, text: str) -> None:
        self.skipped.append(text)

    def print(self) -> int:
        for note in self.notes:
            print(f"note: {note}")
        if self.skipped:
            print(
                f"skipped, as this user may not read them (run with sudo to check): "
                f"{'; '.join(self.skipped)}"
            )
        for text, fix in self.problems:
            print(f"problem: {text}")
            if fix:
                print(f"    fix: {fix}")
        print("All good." if not self.problems else f"{len(self.problems)} problem(s).")
        return 1 if self.problems else 0

    def as_json(self, target: dict[str, Any]) -> dict[str, Any]:
        """The report as one JSON document, for a program to read: the admin service shows it
        (admin/, docs/guide/operations/admin.md). `target` says what was checked."""
        return {
            "target": target,
            "problems": [{"text": text, "fix": fix} for text, fix in self.problems],
            "notes": self.notes,
            "skipped": self.skipped,
        }


def short(sha: str | None) -> str:
    return (sha or "none")[:10]


def journal(unit: str) -> str:
    return f"journalctl -u {unit} -n 50 --no-pager"


@dataclass
class Doctor:
    system: System
    vm: Vm
    report: Report = field(default_factory=Report)

    @property
    def tool(self) -> str:
        return "sudo data-director"

    @property
    def install(self) -> str:
        return (
            f"pull the clone, then sudo {self.vm.clone}/deploy/install.sh "
            f"--domain {domain(self.system, self.vm)}"
        )

    # --- The release ---------------------------------------------------------------------------

    def release(self, live: dict[str, Any] | None) -> None:
        vm, system, report = self.vm, self.system, self.report
        release = vm.live_release()
        if release is None:
            report.problem(f"no release is live: {vm.current} does not exist", self.install)
            return
        sha = release.name
        if live is None:
            report.problem(
                f"the app does not answer on {vm.app_url}/api/about",
                f"systemctl status {APP_UNIT}; {journal(APP_UNIT)}",
            )
        elif live.get("commit") != sha:
            report.problem(
                f"the app runs {short(live.get('commit'))} but {vm.current} points at {short(sha)}: "
                "the last restart did not take effect",
                f"sudo {release}/deploy/deploy.sh --bootstrap (deploy/README.md, "
                '"The app shows an old commit")',
            )
        branch = (read_settings(system, vm.deploy_env) or {}).get("DD_DEPLOY_BRANCH") or "main"
        tip = system.run(
            "git", "-c", "safe.directory=*", "-C", str(vm.bare), "rev-parse", f"refs/heads/{branch}"
        )
        tip_sha = tip.out.strip() if tip.status == 0 else None
        if tip_sha and tip_sha != sha:
            failed = system.read(vm.failed).split() if system.readable(vm.failed) else []
            if tip_sha in failed:
                report.problem(
                    f"{branch}'s tip {short(tip_sha)} failed to deploy, so it is not tried again",
                    f"{journal(DEPLOY_UNIT)}; once fixed, a newer commit deploys by itself",
                )
            else:
                report.note(
                    f"{branch}'s tip {short(tip_sha)} is not live yet ({short(sha)} is): it waits "
                    "for CI or the next pass"
                )
        for unit in ("data-director-deploy.timer", "data-director-restart.path"):
            if not is_active(system, unit):
                report.problem(f"{unit} is not active, so releases stop", self.install)
        if not is_active(system, ADMIN_UNIT):
            report.problem(
                f"{ADMIN_UNIT} is not active, so the admin pages do not answer on 127.0.0.1:8200",
                f"sudo systemctl enable --now {ADMIN_UNIT}; {journal(ADMIN_UNIT)}",
            )
        result = systemctl_show(system, [DEPLOY_UNIT], ["Result"]).get(DEPLOY_UNIT, {})
        if result.get("Result") not in (None, "", "success"):
            report.problem(
                f"the last deployment pass ended with {result['Result']}", journal(DEPLOY_UNIT)
            )
        self.units(release)
        if system.is_root() and system.exists(vm.sudoers):
            report.note(
                f"{vm.sudoers} is no longer used (restarts go through data-director-restart.path); "
                f"remove it: sudo rm {vm.sudoers}"
            )

    def units(self, release: Path) -> None:
        source = release / "deploy" / "systemd"
        if not source.is_dir():
            return
        differ = [
            str(path.relative_to(source))
            for path in sorted(source.rglob("*"))
            if path.is_file()
            and (
                not self.system.readable(self.vm.unit_dir / path.relative_to(source))
                or self.system.read(self.vm.unit_dir / path.relative_to(source))
                != self.system.read(path)
            )
        ]
        if differ:
            self.report.problem(
                f"the installed systemd units differ from the live release's: {', '.join(differ)}",
                self.install,
            )

    # --- The agents ----------------------------------------------------------------------------

    def agents(self, agents: list[Agent]) -> None:
        system, vm, report = self.system, self.vm, self.report
        wanted = wanted_agents(system, vm)
        names = {agent.name for agent in agents}
        units = [agent_unit(agent.name) for agent in agents]
        state = systemctl_show(system, units, ["ActiveState", "UnitFileState", "NRestarts"])
        not_started: list[str] = []
        for agent in agents:
            unit = agent_unit(agent.name)
            shown = state.get(unit, {})
            running = shown.get("ActiveState") == "active"
            expected = agent.name in wanted or shown.get("UnitFileState") == "enabled"
            if not expected:
                if agent.name in MODEL_BACKED:
                    report.note(
                        f"{agent.name} is not turned on (docs/guide/operations/ai-models.md)"
                    )
                elif not running:
                    not_started.append(agent.name)
                continue
            if not running:
                report.problem(f"{unit} is {shown.get('ActiveState') or 'unknown'}", journal(unit))
            elif system.get(f"{agent.url}/.well-known/agent-card.json") is None:
                report.problem(
                    f"{unit} is active but does not answer on port {agent.port}", journal(unit)
                )
            restarts = shown.get("NRestarts", "0")
            if restarts.isdigit() and int(restarts) > 0:
                report.note(f"{unit} has restarted {restarts} time(s) since it was started")
        if not_started:
            report.problem(
                f"data-director.target does not start {', '.join(not_started)}", self.install
            )
        for unit in agent_instances(system):
            name = unit.removeprefix("data-director-agent@").removesuffix(".service")
            if name not in names:
                report.problem(
                    f"{unit} is not an agent in agents.yaml",
                    f"sudo systemctl disable --now '{unit}'; sudo systemctl reset-failed '{unit}'",
                )

    # --- Secrets and settings ------------------------------------------------------------------

    def secrets(self, agents: list[Agent]) -> None:
        system, vm, report = self.system, self.vm, self.report
        wanted = wanted_agents(system, vm)
        state = systemctl_show(system, [agent_unit(a.name) for a in agents], ["UnitFileState"])
        for agent in agents:
            on = (
                agent.name in wanted
                or state.get(agent_unit(agent.name), {}).get("UnitFileState") == "enabled"
            )
            own = read_settings(system, vm.agent_env(agent.name))
            if own is None:
                report.skip(str(vm.agent_env(agent.name)))
                own = {}
            needs = agent.name in MODEL_BACKED or (
                agent.name == "advisor-standards"
                and own.get("DD_STANDARDS_EXPLAINER") == "anthropic"
            )
            if (
                on
                and needs
                and MODEL_KEY not in loaded_secrets(system, vm, agent.name)
                and not any(own.get(var) for var in KEY_VARS)
            ):
                report.problem(
                    f"{agent.name} calls a model but has no key",
                    f"{self.tool} secret set {agent.name} {MODEL_KEY}",
                )
        if system.is_root():
            for directory in sorted(p for p in vm.credentials.glob("*") if p.is_dir()):
                # The app's and the model broker's secrets are not agents'.
                if directory.name in {"app", "model-broker"}:
                    continue
                if directory.name not in {a.name for a in agents}:
                    report.note(f"{directory} belongs to no agent in agents.yaml")
                for file in sorted(directory.iterdir()):
                    if not file.is_file() or file.stat().st_size == 0:
                        report.problem(
                            f"{file} is empty or not a regular file",
                            f"{self.tool} secret set {directory.name} {file.name}",
                        )
        else:
            report.skip(str(vm.credentials))

    def settings(self, release: Path | None) -> None:
        system, vm, report = self.system, self.vm, self.report
        try:
            shared = read_settings(system, vm.agents_env)
        except DevError as exc:
            report.problem(str(exc))
            shared = {}
        if shared is None:
            report.skip(str(vm.agents_env))
        elif leaked := [var for var in KEY_VARS if shared.get(var)]:
            report.problem(
                f"{vm.agents_env} sets {leaked[0]}, which every agent reads",
                f"remove it, then {self.tool} secret set <agent> {MODEL_KEY}",
            )
        try:
            app = read_settings(system, vm.app_env)
        except DevError as exc:
            report.problem(str(exc))
            return
        if app is None:
            report.skip(str(vm.app_env))
            return
        if missing := [name for name in SIGN_IN_SETTINGS if not app.get(name)]:
            report.problem(
                f"{vm.app_env} does not set {', '.join(missing)}, so the app does not start",
                'docs/guide/operations/configuration.md, "Who a run acts for"',
            )
        if [name for name in OPERATOR_SETTINGS if app.get(name)]:
            report.problem(
                f"{vm.app_env} sets an operator (DD_PRINCIPAL_*) beside sign-in, so the app "
                "stops at start-up",
                f"delete the DD_PRINCIPAL_* lines from {vm.app_env}",
            )
        if leaked := [var for var in KEY_VARS if app.get(var)]:
            report.problem(f"{vm.app_env} sets {leaked[0]}; the app holds no model key")
        if system.is_root() and not (
            (vm.credentials / "app" / "orcid-client-secret").is_file()
            and (vm.credentials / "app" / "orcid-client-secret").stat().st_size > 0
        ):
            report.problem(
                "the ORCID client secret is missing",
                f"sudo install -m 0600 /dev/stdin {vm.credentials}/app/orcid-client-secret",
            )
        profile = app.get("DD_PROFILE")
        if profile and release is not None:
            example = release / "app" / "config" / "profile.yaml.example"
            if not system.readable(Path(profile)):
                report.problem(f"DD_PROFILE names {profile}, which cannot be read")
            elif example.is_file():
                notes, problems = compare_profile(Path(profile), example)
                for note in notes:
                    report.note(note)
                for problem in problems:
                    report.problem(problem)

    def config(self) -> None:
        """Whether the instance is what deployment.yaml says (`apply --check`)."""
        system, vm, report = self.system, self.vm, self.report
        place = Place.vm(vm)
        if not system.readable(place.deployment):
            if system.is_root() or system.readable(vm.app_env):
                report.problem(
                    f"no {place.deployment}, so nothing says what this instance runs",
                    f"sudo cp {vm.clone}/config/examples/deployment.yaml {place.deployment}; "
                    f"edit it, then {self.tool} apply",
                )
            else:
                report.skip(str(place.deployment))
            return
        try:
            deployment, planned = plan(system, place, vm)
        except DevError as exc:
            report.problem(str(exc), f"edit {place.deployment}")
            return
        report.note(
            f"{place.deployment} says: {deployment.name}, orchestrator {deployment.orchestrator}"
            + (
                f", disabled {', '.join(sorted(deployment.disabled))}"
                if deployment.disabled
                else ""
            )
        )
        for refusal in planned.refusals:
            report.problem(refusal)
        if pending := planned.pending(system):
            report.problem(
                f"the instance is not yet what {place.deployment.name} says: {', '.join(pending)}",
                f"{self.tool} apply",
            )

    # --- What the app reports ------------------------------------------------------------------

    def live(self, live: dict[str, Any] | None) -> None:
        if live is None:
            return
        report = self.report
        profile = live.get("profile")
        if not isinstance(profile, dict):
            report.note(
                "this release's /api/about does not name its profile or unavailable agents; "
                "a newer release will"
            )
            return
        orchestrator = profile.get("orchestrator")
        report.note(
            f"the app runs profile {profile.get('id')} v{profile.get('version')}, "
            f"conversing with {orchestrator or 'no orchestrator'}"
        )
        if not orchestrator:
            report.problem("the profile names no orchestrator, so the home page cannot converse")
        for state in ("unavailable", "incompatible"):
            for name in live.get(state) or []:
                report.problem(
                    f"the app finds {name} {state}",
                    journal(agent_unit(name)),
                )

    # --- The stores and their backups -----------------------------------------------------------

    def storage(self, now: datetime | None = None) -> None:
        """The backup timer and the newest backup, the free space where the stores and the backups
        are kept, and whether each database a store names answers with this release's schema."""
        system, vm, report = self.system, self.vm, self.report
        if not is_active(system, BACKUP_TIMER):
            report.problem(f"{BACKUP_TIMER} is not active, so nothing is backed up", self.install)
        result = systemctl_show(system, [BACKUP_UNIT], ["Result"]).get(BACKUP_UNIT, {})
        if result.get("Result") not in (None, "", "success"):
            report.problem(f"the last backup ended with {result['Result']}", journal(BACKUP_UNIT))
        for name in ("backup.sh", "stores.sh"):
            source, installed = vm.clone / "deploy" / name, vm.lib / name
            if system.readable(source) and (
                not system.readable(installed) or system.read(installed) != system.read(source)
            ):
                report.problem(f"{installed} is not the clone's deploy/{name}", self.install)
        settings = read_settings(system, vm.backup_env)
        if settings is None:
            report.skip(str(vm.backup_env))
            settings = {}
        backups = Path(settings.get("DD_BACKUP_DIR") or vm.backups)
        newest_size = 0
        if system.is_root():
            names = (
                sorted(
                    p.name for p in backups.iterdir() if p.is_dir() and BACKUP_NAME.match(p.name)
                )
                if backups.is_dir()
                else []
            )
            if not names:
                report.problem(f"there is no backup in {backups}", f"{self.tool} backup")
            else:
                made = datetime.strptime(names[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                age = (now or datetime.now(UTC)) - made
                if age > BACKUP_MAX_AGE:
                    report.problem(
                        f"the newest backup, {backups / names[-1]}, is {age.days} days old",
                        f"{journal(BACKUP_UNIT)}; then {self.tool} backup",
                    )
                newest_size = sum(
                    f.stat().st_size for f in (backups / names[-1]).iterdir() if f.is_file()
                )
        else:
            report.skip(str(backups))
        for path in dict.fromkeys((vm.state, backups)):
            usage = system.disk(path)
            if usage is None:
                continue
            total, free = usage
            if total and free < total * LOW_DISK:
                report.problem(
                    f"the file system holding {path} has {free // 2**20} MiB free, under "
                    f"{LOW_DISK:.0%}",
                    "free space (old releases, the journal) or give the VM a larger disk",
                )
            elif path == backups and free < newest_size:
                report.problem(
                    f"{backups} has {free // 2**20} MiB free, less than the last backup took",
                    "copy the backups off the VM and lower DD_BACKUP_KEEP_DAYS, or free space",
                )
        release = vm.live_release()
        harness = release / ".venv" / "bin" / "dd-harness" if release else None
        databases: dict[str, list[str]] = {}
        for file_name, variable in STORE_SETTINGS:
            file = getattr(vm, file_name)
            found = read_settings(system, file)
            if found is None:
                continue  # skipped above, or reported by settings()
            location = found.get(variable, "")
            if location.startswith("postgresql://"):
                databases.setdefault(
                    location, [f"{k}={v}" for k, v in found.items() if re.fullmatch("PG[A-Z]+", k)]
                )
        for location, libpq in databases.items():
            if harness is None or not system.exists(harness):
                report.skip(f"the schema of {location} (no live release)")
                continue
            done = system.run("env", *libpq, str(harness), "storage", "status", location)
            if done.status != 0:
                said = done.out.strip().splitlines()[-1:] or ["no answer"]
                report.problem(
                    f"the database store {location} does not answer with this release's schema: "
                    f"{said[0]}",
                    "check the database answers (pg_isready), then apply the release's schema "
                    f"as the service user: {harness} storage migrate (docs/specs/storage.md)",
                )

    def nginx(self) -> None:
        system, vm, report = self.system, self.vm, self.report
        if not system.exists(vm.nginx_enabled / "data-director"):
            report.problem("the NGINX site is not enabled", self.install)
        if system.is_root():
            done = system.run("nginx", "-t")
            if done.status != 0:
                report.problem(
                    f"nginx -t fails: {done.out.strip().splitlines()[-1:]}", "sudo nginx -t"
                )

    def run(self, *, as_json: bool = False) -> int:
        """Run every check and print the report: as text, or with `as_json` as one JSON document
        (`Report.as_json`). The status is 1 if there is a problem either way."""
        vm, system = self.vm, self.system
        release = vm.live_release()
        root = system.is_root()
        if not as_json:
            print(f"target: vm ({vm.etc}, release {short(release.name if release else None)})")
            if not root:
                print("note: not run as root, so the settings and secrets are not all checked")
        self.check()
        if as_json:
            target = {
                "kind": "vm",
                "etc": str(vm.etc),
                "release": release.name if release else None,
                "root": root,
            }
            print(json.dumps(self.report.as_json(target), indent=2))
            return 1 if self.report.problems else 0
        return self.report.print()

    def check(self) -> None:
        """Every check, in order, each adding what it finds to `self.report`."""
        vm, system = self.vm, self.system
        release = vm.live_release()
        live = about(system, vm)
        self.release(live)
        try:
            agents = load_agents(vm.source() / "app" / "config" / "agents.yaml")
        except (OSError, KeyError, TypeError) as exc:
            self.report.problem(f"cannot read the release's agents.yaml: {exc}")
            agents = []
        self.config()
        self.agents(agents)
        self.secrets(agents)
        self.settings(release)
        self.live(live)
        self.storage()
        self.nginx()


def vm_doctor(system: System | None = None, vm: Vm | None = None, *, as_json: bool = False) -> int:
    return Doctor(system or System(), vm or Vm()).run(as_json=as_json)
