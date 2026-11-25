"""deploy/deploy.sh picks the newest commit on the branch that passed CI and is newer than the
live one, so a tip still in CI or one that failed does not hold back a commit before it
(deploy/README.md, "Day to day").

The script runs against a VM laid out under tmp_path: a local repository stands in for GitHub,
and stand-ins for curl and systemctl answer the checks API from a table and /api/about with the
release `current` points at. Every release is built in advance, so no pass builds.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "deploy.sh"

pytestmark = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("bash", "flock", "git", "jq")),
    reason="needs bash, flock, git and jq",
)

# Answers the checks API from checks.json ({sha: conclusion}, an absent sha has no run),
# /api/about with the commit `current` points at and the agents missing.json lists for that commit
# ({sha: [agent]}), and /server-status with the turns running (the number in busy, if it exists).
CURL = """#!/usr/bin/env bash
url="${@: -1}"
case "$url" in
  */api/about)
    sha="$(basename "$(readlink "$DD_DEPLOY_ROOT/current")")"
    jq -n --arg sha "$sha" --slurpfile missing "$DD_TEST_MISSING" \
      '{commit: $sha, unavailable: ($missing[0][$sha] // []), incompatible: []}'
    ;;
  */server-status*) echo "BusyWorkers: $(cat "$DD_TEST_BUSY" 2>/dev/null || echo 0)" ;;
  */check-runs)
    sha="$(basename "$(dirname "$url")")"
    echo "$sha" >>"$DD_TEST_ASKED"
    jq --arg sha "$sha" '{check_runs: (if has($sha) then [{conclusion: .[$sha]}] else [] end)}' \
      "$DD_TEST_CHECKS"
    ;;
  *) exit 22 ;;
esac
"""

SYSTEMCTL = """#!/usr/bin/env bash
exit 0
"""


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


@dataclass
class Vm:
    base: Path
    commits: list[str]  # oldest first

    @property
    def root(self) -> Path:
        return self.base / "opt"

    @property
    def checks(self) -> Path:
        return self.base / "checks.json"

    @property
    def asked(self) -> Path:
        return self.base / "asked"

    @property
    def busy(self) -> Path:
        return self.base / "busy"

    @property
    def missing(self) -> Path:
        return self.base / "missing.json"

    def live(self) -> str:
        return (self.root / "current").readlink().name

    def link(self, sha: str) -> None:
        (self.root / "current").symlink_to(self.root / "releases" / sha)

    def answer(self, conclusions: dict[str, str]) -> None:
        self.checks.write_text(json.dumps(conclusions))

    def fail(self, sha: str) -> None:
        (self.root / "failed-commits").write_text(sha + "\n")

    def deploy(self, *args: str, depth: int = 10, **env: str) -> subprocess.CompletedProcess[str]:
        bin_dir = self.base / "bin"
        env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.base),
            "DD_DEPLOY_REPO": str(self.base / "origin"),
            "DD_DEPLOY_ROOT": str(self.root),
            "DD_DEPLOY_DEPTH": str(depth),
            "DD_TEST_CHECKS": str(self.checks),
            "DD_TEST_ASKED": str(self.asked),
            "DD_TEST_BUSY": str(self.busy),
            "DD_TEST_MISSING": str(self.missing),
            **env,
        }
        return subprocess.run(
            ["bash", str(DEPLOY), *args], env=env, capture_output=True, text=True, timeout=60
        )


@pytest.fixture
def vm(tmp_path: Path) -> Vm:
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "--quiet", "--initial-branch=main")
    commits = []
    for n in range(5):
        git(
            origin,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            f"commit {n}",
        )
        commits.append(git(origin, "rev-parse", "HEAD"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, text in (("curl", CURL), ("systemctl", SYSTEMCTL)):
        tool = bin_dir / name
        tool.write_text(text)
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    for sha in commits:
        release = tmp_path / "opt" / "releases" / sha
        (release / "deploy" / "systemd").mkdir(parents=True)
        (release / ".built").write_text(sha + "\n")
    made = Vm(tmp_path, commits)
    made.link(commits[0])
    made.answer({})
    made.missing.write_text("{}")
    return made


def test_a_commit_that_passed_goes_live_while_the_tip_is_in_ci(vm: Vm) -> None:
    *_, passed, failed, tip = vm.commits
    vm.answer({tip: "in_progress", failed: "failure", passed: "success"})

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == passed


def test_the_tip_goes_live_once_it_passes(vm: Vm) -> None:
    tip = vm.commits[-1]
    vm.answer(dict.fromkeys(vm.commits, "success"))

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == tip
    assert vm.asked.read_text().split() == [tip]


def test_a_commit_that_failed_to_start_is_passed_over(vm: Vm) -> None:
    *_, before, tip = vm.commits
    vm.answer({tip: "success", before: "success"})
    vm.fail(tip)

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == before


def test_nothing_older_than_the_live_commit_is_deployed(vm: Vm) -> None:
    older, live, *newer = vm.commits[1:]
    (vm.root / "current").unlink()
    vm.link(live)
    vm.answer({older: "success", **dict.fromkeys(newer, "failure")})

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == live
    assert older not in vm.asked.read_text().split()


def test_a_pass_looks_no_further_back_than_its_depth(vm: Vm) -> None:
    vm.answer({vm.commits[1]: "success"})

    done = vm.deploy(depth=2)

    assert done.returncode == 0, done.stderr
    assert vm.live() == vm.commits[0]
    assert vm.asked.read_text().split() == vm.commits[:-3:-1]


def test_force_deploys_the_tip_without_asking_ci(vm: Vm) -> None:
    tip = vm.commits[-1]
    vm.answer({tip: "failure"})

    done = vm.deploy("--force")

    assert done.returncode == 0, done.stderr
    assert vm.live() == tip
    assert not vm.asked.exists()


@pytest.mark.parametrize("until", ["", "2999-01-01T00:00Z", "next workshop"])
def test_a_pause_holds_deployments_back(vm: Vm, until: str) -> None:
    vm.answer({vm.commits[-1]: "success"})
    (vm.root / "deploy.paused").write_text(until + "\n")

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == vm.commits[0]
    assert not vm.asked.exists()
    assert (vm.root / "deploy.paused").exists()


def test_a_pause_whose_time_has_passed_is_lifted(vm: Vm) -> None:
    tip = vm.commits[-1]
    vm.answer({tip: "success"})
    (vm.root / "deploy.paused").write_text("2000-01-01T00:00Z\n")

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == tip
    assert not (vm.root / "deploy.paused").exists()


def test_force_deploys_through_a_pause(vm: Vm) -> None:
    (vm.root / "deploy.paused").write_text("")

    done = vm.deploy("--force")

    assert done.returncode == 0, done.stderr
    assert vm.live() == vm.commits[-1]


def test_a_build_waits_while_memory_is_short_and_records_no_failure(vm: Vm) -> None:
    tip = vm.commits[-1]
    (vm.root / "releases" / tip / ".built").unlink()
    vm.answer({tip: "success"})
    meminfo = vm.base / "meminfo"
    meminfo.write_text("MemTotal: 3900000 kB\nMemAvailable: 204800 kB\n")

    done = vm.deploy(DD_DEPLOY_MEMINFO=str(meminfo))

    assert done.returncode == 0, done.stderr
    assert vm.live() == vm.commits[0]
    assert not (vm.root / "releases" / tip / ".built").exists()
    assert not (vm.root / "failed-commits").exists()


def test_a_release_waits_for_the_turns_running(vm: Vm) -> None:
    vm.answer(dict.fromkeys(vm.commits, "success"))
    vm.busy.write_text("2")

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == vm.commits[0]
    assert not (vm.root / "failed-commits").exists()

    vm.busy.write_text("0")
    assert vm.deploy().returncode == 0
    assert vm.live() == vm.commits[-1]


def test_a_release_waits_for_the_turns_only_so_long(vm: Vm) -> None:
    tip = vm.commits[-1]
    vm.answer({tip: "success"})
    vm.busy.write_text("2")
    built = vm.root / "releases" / tip / ".built"
    os.utime(built, (0, 0))

    done = vm.deploy()

    assert done.returncode == 0, done.stderr
    assert vm.live() == tip


def test_force_does_not_wait_for_the_turns_running(vm: Vm) -> None:
    vm.busy.write_text("2")

    assert vm.deploy("--force").returncode == 0
    assert vm.live() == vm.commits[-1]


def test_a_release_whose_agent_does_not_start_is_rolled_back(vm: Vm) -> None:
    tip = vm.commits[-1]
    vm.answer({tip: "success"})
    vm.missing.write_text(json.dumps({tip: ["advisor-quality"]}))

    done = vm.deploy(DD_DEPLOY_HEALTH_TIMEOUT="1")

    assert done.returncode != 0
    assert vm.live() == vm.commits[0]
    assert tip in (vm.root / "failed-commits").read_text().split()


def test_an_agent_that_was_already_down_does_not_roll_a_release_back(vm: Vm) -> None:
    first, tip = vm.commits[0], vm.commits[-1]
    vm.answer({tip: "success"})
    vm.missing.write_text(json.dumps({first: ["advisor-quality"], tip: ["advisor-quality"]}))

    done = vm.deploy(DD_DEPLOY_HEALTH_TIMEOUT="1")

    assert done.returncode == 0, done.stderr
    assert vm.live() == tip
