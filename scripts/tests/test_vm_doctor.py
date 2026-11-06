"""`dd.py doctor` on a VM (scripts/ddtool/vm_doctor.py), against a VM laid out under tmp_path and
a stand-in for systemd, git and the app."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ddtool.vm import Done, System, Vm  # noqa: E402
from ddtool.vm_doctor import Doctor  # noqa: E402

SHA = "a" * 40
TIP = "b" * 40
AGENTS = """agents:
  - name: example-hello
    url: http://127.0.0.1:8101/
  - name: orchestrator-model
    url: http://127.0.0.1:8107/
"""
TARGET = """[Unit]
Description=Data Director (app and agents)
Wants=data-director-app.service
Wants=data-director-agent@example-hello.service
"""
PROFILE = {
    "id": "data-director-app",
    "version": 7,
    "digest": "d",
    "orchestrator": "orchestrator.stub",
}


@dataclass
class FakeVm(System):
    """systemd, git, NGINX and HTTP as a healthy VM answers them; tests change what they need."""

    root: bool = True
    units: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "data-director-agent@example-hello.service": {
                "ActiveState": "active",
                "UnitFileState": "static",
                "NRestarts": "0",
            },
            "data-director-agent@orchestrator-model.service": {
                "ActiveState": "inactive",
                "UnitFileState": "disabled",
                "NRestarts": "0",
            },
            "data-director-deploy.service": {"Result": "success"},
        }
    )
    active: set[str] = field(
        default_factory=lambda: {"data-director-deploy.timer", "data-director-restart.path"}
    )
    instances: list[str] = field(
        default_factory=lambda: ["data-director-agent@example-hello.service"]
    )
    tip: str = SHA
    about: dict[str, Any] | None = field(
        default_factory=lambda: {
            "commit": SHA,
            "profile": dict(PROFILE),
            "unavailable": [],
            "incompatible": [],
        }
    )
    answering: set[int] = field(default_factory=lambda: {8101})

    def run(self, *cmd: str) -> Done:
        match cmd:
            case ("systemctl", "show", *rest):
                units = [word for word in rest if not word.startswith("--")]
                blocks = [
                    "\n".join(
                        [f"Id={unit}", *(f"{k}={v}" for k, v in self.units.get(unit, {}).items())]
                    )
                    for unit in units
                ]
                return Done(0, "\n\n".join(blocks) + "\n")
            case ("systemctl", "is-active", "--quiet", unit):
                return Done(0 if unit in self.active else 3, "")
            case ("systemctl", "list-units", *_):
                return Done(0, "".join(f"{u} loaded active running x\n" for u in self.instances))
            case ("git", *_):
                return Done(0, self.tip + "\n")
            case ("nginx", "-t"):
                return Done(0, "syntax is ok")
        raise AssertionError(f"unexpected command {cmd}")

    def get(self, url: str) -> str | None:
        if url.endswith("/api/about"):
            return None if self.about is None else json.dumps(self.about)
        port = int(url.split(":")[2].split("/")[0])
        return "{}" if port in self.answering else None

    def is_root(self) -> bool:
        return self.root


@pytest.fixture
def vm(tmp_path: Path) -> Vm:
    """A VM as install.sh leaves it, with one release live."""
    layout = Vm(
        etc=tmp_path / "etc",
        unit_dir=tmp_path / "systemd",
        root=tmp_path / "opt",
        nginx_enabled=tmp_path / "nginx" / "enabled",
        nginx_available=tmp_path / "nginx" / "available",
        sudoers=tmp_path / "sudoers",
        clone=tmp_path / "clone",
    )
    release = layout.releases / SHA
    (release / "app" / "config").mkdir(parents=True)
    (release / "app" / "config" / "agents.yaml").write_text(AGENTS)
    (release / "deploy" / "systemd").mkdir(parents=True)
    (release / "deploy" / "systemd" / "data-director.target").write_text(TARGET)
    layout.current.symlink_to(release)
    layout.unit_dir.mkdir()
    (layout.unit_dir / "data-director.target").write_text(TARGET)
    (layout.credentials / "app").mkdir(parents=True)
    (layout.credentials / "app" / "orcid-client-secret").write_text("s3cret")
    layout.app_env.write_text(
        "DD_OIDC_ISSUER=https://orcid.org\nDD_OIDC_CLIENT_ID=APP-1\n"
        "DD_APP_PUBLIC_URL=https://dd.example.ac.uk\n"
    )
    layout.agents_env.write_text("")
    for site in (layout.nginx_enabled, layout.nginx_available):
        site.mkdir(parents=True)
        (site / "data-director").write_text("server_name dd.example.ac.uk;\n")
    return layout


def check(system: FakeVm, vm: Vm, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    status = Doctor(system, vm).run()
    return status, capsys.readouterr().out


def test_a_healthy_vm_is_all_good(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    status, out = check(FakeVm(), vm, capsys)
    assert status == 0, out
    assert "All good." in out
    assert "orchestrator-model is not turned on" in out
    assert "conversing with orchestrator.stub" in out


def test_an_old_commit_still_running_names_the_bootstrap(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.about = {**(system.about or {}), "commit": "c" * 40}
    status, out = check(system, vm, capsys)
    assert status == 1
    assert "the app runs cccccccccc but" in out
    assert f"releases/{SHA}/deploy/deploy.sh --bootstrap" in out


def test_a_tip_that_failed_is_a_problem_and_a_waiting_one_a_note(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(tip=TIP), vm, capsys)
    assert status == 0 and "is not live yet" in out
    vm.failed.write_text(TIP + "\n")
    status, out = check(FakeVm(tip=TIP), vm, capsys)
    assert status == 1 and "failed to deploy" in out


def test_a_stray_instance_is_named_with_how_to_remove_it(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    stray = "data-director-agent@orchestrator-model.servic.service"
    system = FakeVm()
    system.instances.append(stray)
    status, out = check(system, vm, capsys)
    assert status == 1
    assert f"{stray} is not an agent in agents.yaml" in out
    assert f"systemctl disable --now '{stray}'" in out


def test_a_model_backed_agent_turned_on_without_a_key_names_the_secret_command(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.units["data-director-agent@orchestrator-model.service"] = {
        "ActiveState": "failed",
        "UnitFileState": "enabled",
        "NRestarts": "3",
    }
    status, out = check(system, vm, capsys)
    assert status == 1
    assert "orchestrator-model calls a model but has no key" in out
    assert "data-director secret set orchestrator-model anthropic-api-key" in out
    assert "data-director-agent@orchestrator-model.service is failed" in out


def test_a_key_loaded_by_the_drop_in_is_enough(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    system = FakeVm(answering={8101, 8107})
    system.units["data-director-agent@orchestrator-model.service"] = {
        "ActiveState": "active",
        "UnitFileState": "enabled",
        "NRestarts": "0",
    }
    dropin = vm.credentials_dropin("orchestrator-model")
    dropin.parent.mkdir(parents=True)
    dropin.write_text("[Service]\nLoadCredential=anthropic-api-key:/etc/x\n")
    status, out = check(system, vm, capsys)
    assert status == 0, out


def test_an_agent_the_app_cannot_reach_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.about = {**(system.about or {}), "unavailable": ["example-hello"]}
    status, out = check(system, vm, capsys)
    assert status == 1
    assert "the app finds example-hello unavailable" in out


def test_an_app_that_does_not_answer_names_its_journal(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(about=None), vm, capsys)
    assert status == 1
    assert "journalctl -u data-director-app.service" in out


def test_units_that_differ_from_the_release_name_install_sh(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.unit_dir / "data-director.target").write_text(TARGET + "# edited\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert "differ from the live release's: data-director.target" in out
    assert "install.sh --domain dd.example.ac.uk" in out


def test_sign_in_settings_and_operator_lines_are_checked(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    vm.app_env.write_text("DD_PRINCIPAL_ID=https://orcid.org/0000-0002-1825-0097\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert "does not set DD_OIDC_ISSUER, DD_OIDC_CLIENT_ID, DD_APP_PUBLIC_URL" in out
    assert "sets an operator" in out


def test_a_key_in_the_shared_settings_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    vm.agents_env.write_text("ANTHROPIC_API_KEY=sk-ant-x\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert "sets ANTHROPIC_API_KEY, which every agent reads" in out
    assert "sk-ant-x" not in out


def test_without_root_what_cannot_be_read_is_skipped(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(root=False), vm, capsys)
    assert status == 0, out
    assert "not run as root" in out
    assert "skipped" in out and str(vm.credentials) in out


def test_no_live_release_is_a_problem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = Vm(
        etc=tmp_path / "etc",
        root=tmp_path / "opt",
        unit_dir=tmp_path / "u",
        nginx_enabled=tmp_path / "n",
        nginx_available=tmp_path / "n",
        clone=ROOT,
    )
    status, out = check(FakeVm(about=None, instances=[]), empty, capsys)
    assert status == 1
    assert "no release is live" in out
