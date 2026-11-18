"""`dd.py doctor` on a VM: check the deployment, its services, its secrets and the live app, and
name the command that fixes each problem. It changes nothing.

Run as root to check everything: the settings files and secrets are root's. As another user it
checks what that user can read and says what it skipped.

The report and what the checks share are in `vm_report`; the checks of the operator's settings and
secrets are in `vm_settings`.
"""

from __future__ import annotations

import json
import re
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ddtool.common import MODEL_BACKED, Agent, load_agents
from ddtool.vm import (
    System,
    Vm,
    about,
    agent_instances,
    agent_unit,
    is_active,
    read_settings,
    systemctl_show,
    wanted_agents,
)
from ddtool.vm_report import journal, short
from ddtool.vm_settings import SettingsChecks

APP_UNIT = "data-director-app.service"
DEPLOY_UNIT = "data-director-deploy.service"
ADMIN_UNIT = "data-director-admin.service"
BACKUP_UNIT = "data-director-backup.service"
BACKUP_TIMER = "data-director-backup.timer"
BROKER_UNIT = "data-director-model-broker.service"
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


class Doctor(SettingsChecks):
    """Every check of a VM, in the order `check` runs them."""

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

    # --- The model broker ----------------------------------------------------------------------

    def broker(self) -> None:
        """The broker runs as a user of its own, so every directory on the way to the release's
        interpreter must let others through (docs/guide/operations/model-broker.md)."""
        state = systemctl_show(self.system, [BROKER_UNIT], ["UnitFileState"])
        release = self.vm.live_release()
        if state.get(BROKER_UNIT, {}).get("UnitFileState") != "enabled" or release is None:
            return
        python = release / ".venv" / "bin" / "python"
        if not python.exists():
            return
        interpreter = python.resolve()
        # The directories above the deployment's own, such as /opt and /var/lib, are the system's.
        system_dirs = set(self.vm.root.parents)
        for directory in reversed(interpreter.parents):
            if directory in system_dirs:
                continue
            if not directory.stat().st_mode & stat.S_IXOTH:
                self.report.problem(
                    f"{BROKER_UNIT} cannot run the release's Python, {interpreter}: "
                    f"{directory} lets no other user through",
                    self.install,
                )
                return

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
        self._backup_service()
        settings = read_settings(system, vm.backup_env)
        if settings is None:
            report.skip(str(vm.backup_env))
            settings = {}
        backups = Path(settings.get("DD_BACKUP_DIR") or vm.backups)
        newest_size = 0
        if system.is_root():
            newest_size = self._newest_backup(backups, now)
        else:
            report.skip(str(backups))
        self._disk_space(backups, newest_size)
        self._databases()

    def _backup_service(self) -> None:
        """The backup timer is on, its last pass succeeded and its scripts are the clone's."""
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

    def _newest_backup(self, backups: Path, now: datetime | None) -> int:
        """Whether there is a recent backup in `backups`; the size of the newest, or 0."""
        report = self.report
        names = (
            sorted(p.name for p in backups.iterdir() if p.is_dir() and BACKUP_NAME.match(p.name))
            if backups.is_dir()
            else []
        )
        if not names:
            report.problem(f"there is no backup in {backups}", f"{self.tool} backup")
            return 0
        made = datetime.strptime(names[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        age = (now or datetime.now(UTC)) - made
        if age > BACKUP_MAX_AGE:
            report.problem(
                f"the newest backup, {backups / names[-1]}, is {age.days} days old",
                f"{journal(BACKUP_UNIT)}; then {self.tool} backup",
            )
        return sum(f.stat().st_size for f in (backups / names[-1]).iterdir() if f.is_file())

    def _disk_space(self, backups: Path, newest_size: int) -> None:
        """Room on the file systems that hold the stores and the backups."""
        system, vm, report = self.system, self.vm, self.report
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

    def _databases(self) -> None:
        """Each database a store names answers with the live release's schema."""
        system, vm, report = self.system, self.vm, self.report
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
        self.broker()
        self.secrets(agents)
        self.settings(release)
        self.live(live)
        self.storage()
        self.nginx()


def vm_doctor(system: System | None = None, vm: Vm | None = None, *, as_json: bool = False) -> int:
    return Doctor(system or System(), vm or Vm()).run(as_json=as_json)
