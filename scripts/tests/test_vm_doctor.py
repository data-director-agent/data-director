"""`dd.py doctor` on a VM (scripts/ddtool/vm_doctor.py), against a VM laid out under tmp_path and
a stand-in for systemd, git and the app."""

from __future__ import annotations

import grp
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ddtool.common import DevError  # noqa: E402
from ddtool.deployment import Place, apply, plan  # noqa: E402
from ddtool.vm import Done, System, Vm  # noqa: E402
from ddtool.vm_doctor import Doctor  # noqa: E402

EXAMPLE_PROFILE = ROOT / "app" / "config" / "profile.yaml.example"

SHA = "a" * 40
TIP = "b" * 40
AGENTS = """agents:
  - name: example-hello
    url: http://127.0.0.1:8101/
  - name: orchestrator-stub
    url: http://127.0.0.1:8106/
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
            "data-director-agent@orchestrator-stub.service": {
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
            "data-director-backup.service": {"Result": "success"},
        }
    )
    active: set[str] = field(
        default_factory=lambda: {
            "data-director-deploy.timer",
            "data-director-restart.path",
            "data-director-backup.timer",
            "data-director-admin.service",
        }
    )
    # The size of each file system and the bytes free on it.
    free: tuple[int, int] = (100 * 2**30, 50 * 2**30)
    # What `dd-harness storage status` answers.
    schema: Done = field(default_factory=lambda: Done(0, "version 3, this build expects 3"))
    instances: list[str] = field(
        default_factory=lambda: [
            "data-director-agent@example-hello.service",
            "data-director-agent@orchestrator-stub.service",
        ]
    )
    calls: list[tuple[str, ...]] = field(default_factory=list)
    tip: str = SHA
    about: dict[str, Any] | None = field(
        default_factory=lambda: {
            "commit": SHA,
            "profile": dict(PROFILE),
            "unavailable": [],
            "incompatible": [],
        }
    )
    answering: set[int] = field(default_factory=lambda: {8101, 8106})
    # Docker's networks as `docker network inspect` shows them, and the bridge interfaces as
    # `ip -json address` shows them: a healthy VM's are outside the campus ranges. `docker` is
    # what `docker network ls` answers (127: Docker is not installed).
    docker_networks: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "Name": "data-director-llm-gateway_default",
                "IPAM": {"Config": [{"Subnet": "10.201.0.0/24"}]},
            }
        ]
    )
    bridges: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "ifname": "br-1",
                "operstate": "UP",
                "addr_info": [{"local": "10.201.0.1", "prefixlen": 24}],
            }
        ]
    )
    docker: int = 0

    def run(self, *cmd: str) -> Done:
        match cmd:
            case ("docker", "network", "ls", "-q"):
                return Done(self.docker, "abc\n" if self.docker == 0 else "")
            case ("docker", "network", "inspect", *_):
                return Done(0, json.dumps(self.docker_networks))
            case ("ip", "-json", "-4", "address", "show", "type", "bridge"):
                return Done(0, json.dumps(self.bridges))
            case ("env", *rest) if rest[-3:-1] == ["storage", "status"]:
                self.calls.append(cmd)
                return self.schema
            case ("env", *_) | ("systemctl", "daemon-reload" | "disable" | "restart", *_):
                self.calls.append(cmd)
                return Done(0, "")
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

    def disk(self, path: Path) -> tuple[int, int] | None:
        return self.free


def make_backup(vm: Vm, age: timedelta = timedelta(hours=3)) -> Path:
    made = vm.backups / (datetime.now(UTC) - age).strftime("%Y%m%dT%H%M%SZ")
    made.mkdir(parents=True)
    (made / "config.tar.gz").write_bytes(b"x" * 1024)
    return made


@pytest.fixture
def vm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Vm:
    """A VM as install.sh leaves it, with one release live."""
    # Run as root, `apply` gives its files to the service group, which only a real VM has.
    monkeypatch.setattr(grp, "getgrnam", lambda _name: grp.getgrgid(os.getgid()))
    layout = Vm(
        etc=tmp_path / "etc",
        unit_dir=tmp_path / "systemd",
        root=tmp_path / "opt",
        nginx_enabled=tmp_path / "nginx" / "enabled",
        nginx_available=tmp_path / "nginx" / "available",
        sudoers=tmp_path / "sudoers",
        clone=tmp_path / "clone",
        state=tmp_path / "state",
        backups=tmp_path / "backups",
        lib=tmp_path / "lib",
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
    shutil.copyfile(EXAMPLE_PROFILE, release / "app" / "config" / "profile.yaml.example")
    (layout.etc / "deployment.yaml").write_text("name: test\norchestrator: stub\n")
    # As `apply` left it, after a night's backup.
    assert apply(FakeVm(), Place.vm(layout), layout) == 0
    make_backup(layout)
    return layout


def check(system: FakeVm, vm: Vm, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    status = Doctor(system, vm).run()
    return status, capsys.readouterr().out


def says(out: str, kind: str, *tokens: str) -> bool:
    """Whether one line of the output of this kind (problem, fix, note, skipped, refused) names
    every token."""
    return any(
        line.strip().startswith(kind) and all(token in line for token in tokens)
        for line in out.splitlines()
    )


def test_a_healthy_vm_is_all_good(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    status, out = check(FakeVm(), vm, capsys)
    assert status == 0, out
    assert "All good." in out
    assert says(out, "note", "orchestrator-model")
    assert says(out, "note", "orchestrator.stub")


def network(name: str, subnet: str) -> dict[str, Any]:
    return {"Name": name, "IPAM": {"Config": [{"Subnet": subnet}]}}


def bridge(ifname: str, address: str, state: str = "UP") -> dict[str, Any]:
    local, _, length = address.partition("/")
    return {
        "ifname": ifname,
        "operstate": state,
        "addr_info": [{"local": local, "prefixlen": int(length)}],
    }


def test_a_docker_network_in_a_campus_range_is_a_problem_with_its_fix(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(
        docker_networks=[network("monitoring_default", "172.18.0.0/16")],
        bridges=[bridge("br-2", "172.18.0.1/16")],
    )
    status, out = check(system, vm, capsys)
    assert status == 1, out
    assert says(out, "problem", "monitoring_default", "172.18.0.0/16", "172.16.0.0/12")
    assert says(out, "fix", "bip", "default-address-pools", "daemon.json")
    assert not says(out, "fix", "DD_GATEWAY_SUBNET")


def test_the_gateway_network_in_a_campus_range_names_its_own_setting(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(
        docker_networks=[network("data-director-llm-gateway_default", "192.168.16.0/20")],
        bridges=[bridge("br-3", "192.168.16.1/20")],
    )
    status, out = check(system, vm, capsys)
    assert status == 1, out
    assert says(out, "fix", "DD_GATEWAY_SUBNET", "default-address-pools")


def test_a_bridge_whose_link_is_down_is_a_note_not_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(
        docker_networks=[network("bridge", "172.17.0.0/16")],
        bridges=[bridge("docker0", "172.17.0.1/16", "DOWN")],
    )
    status, out = check(system, vm, capsys)
    assert status == 0, out
    assert says(out, "note", "bridge", "172.17.0.0/16", "down")


def test_a_bridge_docker_does_not_list_is_found_by_its_interface(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(docker_networks=[], bridges=[bridge("br-old", "172.19.0.1/16")])
    status, out = check(system, vm, capsys)
    assert status == 1, out
    assert says(out, "problem", "br-old", "172.19.0.0/16")


def test_deployment_campus_ranges_replace_the_defaults(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.etc / "deployment.yaml").write_text(
        "name: test\norchestrator: stub\ncampus_ranges: [10.0.0.0/8]\n"
    )
    system = FakeVm(
        docker_networks=[network("a", "172.18.0.0/16"), network("b", "10.5.0.0/24")],
        bridges=[bridge("br-a", "172.18.0.1/16"), bridge("br-b", "10.5.0.1/24")],
    )
    _status, out = check(system, vm, capsys)
    assert says(out, "problem", "b", "10.5.0.0/24", "10.0.0.0/8")
    assert not says(out, "problem", "172.18.0.0/16")


def test_a_vm_without_docker_reports_no_network(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    system = FakeVm(docker=127, bridges=[])
    status, out = check(system, vm, capsys)
    assert status == 0, out
    assert not says(out, "skipped", "Docker")


def test_a_refusing_docker_is_skipped(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    status, out = check(FakeVm(docker=1, root=False), vm, capsys)
    assert "Docker networks" in out
    assert status in (0, 1)


def test_a_network_problem_is_in_the_json_report(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(
        docker_networks=[network("monitoring_default", "172.18.0.0/16")],
        bridges=[bridge("br-2", "172.18.0.1/16")],
    )
    Doctor(system, vm).run(as_json=True)
    report = json.loads(capsys.readouterr().out)
    assert any(
        "monitoring_default" in p["text"] and "default-address-pools" in (p["fix"] or "")
        for p in report["problems"]
    )


def link_python(vm: Vm, home: Path, mode: int) -> None:
    """Give the live release a .venv whose python links to an interpreter in `home`, made `mode`."""
    interpreter = home / "python" / "bin" / "python3.14"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("")
    home.chmod(mode)
    venv = vm.releases / SHA / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(interpreter)


def broker_enabled() -> FakeVm:
    system = FakeVm()
    system.units["data-director-model-broker.service"] = {"UnitFileState": "enabled"}
    return system


def test_an_enabled_broker_that_cannot_reach_python_names_install_sh(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    link_python(vm, vm.state, 0o750)
    status, out = check(broker_enabled(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "data-director-model-broker.service", str(vm.state))
    assert says(out, "fix", "install.sh")


def test_an_enabled_broker_with_python_beside_the_releases_is_all_good(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    link_python(vm, vm.root / "python", 0o755)
    status, out = check(broker_enabled(), vm, capsys)
    assert status == 0, out


def test_a_broker_not_enabled_is_not_checked(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    link_python(vm, vm.state, 0o750)
    status, out = check(FakeVm(), vm, capsys)
    assert status == 0, out


GATEWAY = "http://127.0.0.1:4000"


def point_the_broker_at_the_gateway(vm: Vm) -> None:
    (vm.etc / "model-broker.env").write_text(f"DD_BROKER_DEPLOYMENT_BASE_URL={GATEWAY}\n")


def test_a_broker_sent_to_a_gateway_that_is_not_installed_names_install_sh_gateway(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    point_the_broker_at_the_gateway(vm)
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", GATEWAY, "DD_BROKER_DEPLOYMENT_BASE_URL")
    assert says(out, "fix", "install.sh", "--gateway")


def test_a_gateway_installed_but_not_answering_names_its_journal(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    point_the_broker_at_the_gateway(vm)
    system = FakeVm()
    system.units["data-director-llm-gateway.service"] = {"UnitFileState": "enabled"}
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "fix", "journalctl", "data-director-llm-gateway.service")


def test_an_agent_sent_to_a_gateway_that_answers_is_all_good(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.etc / "agents").mkdir(exist_ok=True)
    (vm.etc / "agents" / "advisor-standards.env").write_text(f"ANTHROPIC_BASE_URL={GATEWAY}\n")
    system = FakeVm()
    system.answering.add(4000)
    status, out = check(system, vm, capsys)
    assert status == 0, out
    assert not says(out, "problem", GATEWAY)


def test_an_old_commit_still_running_names_the_bootstrap(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.about = {**(system.about or {}), "commit": "c" * 40}
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", "cccccccccc")
    assert says(out, "fix", f"releases/{SHA}/deploy/deploy.sh --bootstrap")


def test_a_tip_that_failed_is_a_problem_and_a_waiting_one_a_note(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(tip=TIP), vm, capsys)
    assert status == 0 and says(out, "note", TIP[:10])
    vm.failed.write_text(TIP + "\n")
    status, out = check(FakeVm(tip=TIP), vm, capsys)
    assert status == 1 and says(out, "problem", TIP[:10])


def test_a_pause_is_a_note(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    vm.paused.write_text("2026-11-24T18:00Z\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 0, out
    assert says(out, "note", "2026-11-24T18:00Z", str(vm.paused))


def test_a_stray_instance_is_named_with_how_to_remove_it(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    stray = "data-director-agent@orchestrator-model.servic.service"
    system = FakeVm()
    system.instances.append(stray)
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", stray, "agents.yaml")
    assert says(out, "fix", f"systemctl disable --now '{stray}'")


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
    assert says(out, "fix", "data-director secret set orchestrator-model anthropic-api-key")
    assert says(out, "problem", "data-director-agent@orchestrator-model.service", "failed")


def test_a_key_loaded_by_the_drop_in_is_enough(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    system = FakeVm(answering={8101, 8106, 8107})
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


def test_the_orchestrator_on_another_provider_names_that_providers_secret(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(answering={8101, 8106, 8107})
    system.units["data-director-agent@orchestrator-model.service"] = {
        "ActiveState": "active",
        "UnitFileState": "enabled",
        "NRestarts": "0",
    }
    settings = vm.agent_env("orchestrator-model")
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("DD_MODEL_PROVIDER=openai\nDD_MODEL_ID=gpt-test\n")
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "fix", "data-director secret set orchestrator-model openai-api-key")


def test_the_orchestrator_on_an_openai_compatible_endpoint_may_have_no_key(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm(answering={8101, 8106, 8107})
    system.units["data-director-agent@orchestrator-model.service"] = {
        "ActiveState": "active",
        "UnitFileState": "enabled",
        "NRestarts": "0",
    }
    settings = vm.agent_env("orchestrator-model")
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        "DD_MODEL_PROVIDER=openai-compatible\nDD_MODEL_ID=llama3.3\n"
        "DD_MODEL_BASE_URL=http://localhost:11434/v1\n"
    )
    status, out = check(system, vm, capsys)
    assert status == 0, out


def test_an_agent_the_app_cannot_reach_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.about = {**(system.about or {}), "unavailable": ["example-hello"]}
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", "example-hello", "unavailable")


def test_an_app_that_does_not_answer_names_its_journal(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(about=None), vm, capsys)
    assert status == 1
    assert says(out, "fix", "journalctl -u data-director-app.service")


def test_units_that_differ_from_the_release_name_install_sh(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.unit_dir / "data-director.target").write_text(TARGET + "# edited\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "data-director.target")
    assert says(out, "fix", "install.sh --domain dd.example.ac.uk")


def test_sign_in_settings_and_operator_lines_are_checked(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    vm.app_env.write_text("DD_PRINCIPAL_ID=https://orcid.org/0000-0002-1825-0097\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "DD_OIDC_ISSUER", "DD_OIDC_CLIENT_ID", "DD_APP_PUBLIC_URL")
    assert says(out, "problem", "DD_PRINCIPAL_")


def test_a_key_in_the_shared_settings_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    vm.agents_env.write_text("ANTHROPIC_API_KEY=sk-ant-x\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", str(vm.agents_env), "ANTHROPIC_API_KEY")
    assert "sk-ant-x" not in out


def test_without_root_what_cannot_be_read_is_skipped(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(root=False), vm, capsys)
    assert status == 0, out
    assert says(out, "note", "root")
    assert says(out, "skipped", str(vm.credentials))


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
    assert says(out, "problem", "no release")


# --- deployment.yaml and apply ------------------------------------------------------------------


def example_version() -> int:
    found = re.search(r"^version: (\d+)", EXAMPLE_PROFILE.read_text(), re.MULTILINE)
    assert found
    return int(found[1])


def test_apply_writes_the_profile_the_units_and_dd_profile(vm: Vm) -> None:
    profile = (vm.etc / "profile.yaml").read_text()
    assert "\nprofile_id: data-director-app-test\n" in profile
    assert "\norchestrator: orchestrator.stub\n" in profile
    assert f"\nversion: {example_version() + 1}\n" in profile
    assert f"DD_PROFILE={vm.etc / 'profile.yaml'}" in vm.app_env.read_text()
    wants = (vm.unit_dir / "data-director.target.d" / "agents.conf").read_text()
    assert "Wants=data-director-agent@example-hello.service" in wants
    assert "Wants=data-director-agent@orchestrator-stub.service" in wants
    assert "orchestrator-model" not in wants  # model-backed: only as the orchestrator
    app = (vm.unit_dir / "data-director-app.service.d" / "agents.conf").read_text()
    assert 'Environment="DD_WAIT_PORTS=8101 8106"' in app
    workbench = (vm.unit_dir / "data-director-workbench.service.d" / "agents.conf").read_text()
    assert workbench == app


def test_apply_again_changes_nothing_and_keeps_the_version(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (vm.etc / "profile.yaml").read_text()
    system = FakeVm()
    assert apply(system, Place.vm(vm), vm, check=True) == 0
    assert apply(system, Place.vm(vm), vm) == 0
    assert "Nothing to change." in capsys.readouterr().out
    assert (vm.etc / "profile.yaml").read_text() == before
    assert not system.calls  # no reload, no restart


NOTICE = "https://example.ac.uk/data-director/privacy"


def test_apply_writes_the_privacy_notice_to_app_env_and_leaves_the_profile_alone(vm: Vm) -> None:
    profile = (vm.etc / "profile.yaml").read_text()
    assert "DD_PRIVACY_NOTICE_URL" not in vm.app_env.read_text()  # unset: no setting
    (vm.etc / "deployment.yaml").write_text(
        f"name: test\norchestrator: stub\nprivacy_notice: {NOTICE}\n"
    )
    assert apply(FakeVm(), Place.vm(vm), vm) == 0
    assert f"DD_PRIVACY_NOTICE_URL={NOTICE}" in vm.app_env.read_text()
    assert f"DD_PROFILE={vm.etc / 'profile.yaml'}" in vm.app_env.read_text()  # kept
    # A display address is not policy: the profile and so its digest and version are unchanged.
    assert (vm.etc / "profile.yaml").read_text() == profile


def test_apply_again_with_a_privacy_notice_changes_nothing(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.etc / "deployment.yaml").write_text(
        f"name: test\norchestrator: stub\nprivacy_notice: {NOTICE}\n"
    )
    assert apply(FakeVm(), Place.vm(vm), vm) == 0
    capsys.readouterr()
    assert apply(FakeVm(), Place.vm(vm), vm, check=True) == 0
    assert "Nothing to change." in capsys.readouterr().out


def test_removing_the_privacy_notice_removes_the_setting_and_nothing_else(vm: Vm) -> None:
    (vm.etc / "deployment.yaml").write_text(
        f"name: test\norchestrator: stub\nprivacy_notice: {NOTICE}\n"
    )
    assert apply(FakeVm(), Place.vm(vm), vm) == 0
    before = vm.app_env.read_text()
    assert "DD_PRIVACY_NOTICE_URL" in before
    (vm.etc / "deployment.yaml").write_text("name: test\norchestrator: stub\n")
    assert apply(FakeVm(), Place.vm(vm), vm) == 0
    after = vm.app_env.read_text()
    assert "DD_PRIVACY_NOTICE_URL" not in after
    assert after == before.replace(f"DD_PRIVACY_NOTICE_URL={NOTICE}\n", "")


def test_doctor_reports_a_privacy_notice_not_yet_applied(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.etc / "deployment.yaml").write_text(
        f"name: test\norchestrator: stub\nprivacy_notice: {NOTICE}\n"
    )
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "DD_PRIVACY_NOTICE_URL")
    assert says(out, "fix", "data-director apply")


def test_the_model_orchestrator_is_refused_without_its_key(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.etc / "deployment.yaml").write_text("name: test\norchestrator: model\n")
    before = (vm.etc / "profile.yaml").read_text()
    assert apply(FakeVm(), Place.vm(vm), vm) == 1
    out = capsys.readouterr().out
    assert says(out, "refused", "data-director secret set orchestrator-model anthropic-api-key")
    assert (vm.etc / "profile.yaml").read_text() == before


def test_the_model_orchestrator_with_its_key_is_started_and_waited_for(vm: Vm) -> None:
    (vm.etc / "deployment.yaml").write_text("name: test\norchestrator: model\n")
    (vm.credentials / "orchestrator-model").mkdir()
    (vm.credentials / "orchestrator-model" / "anthropic-api-key").write_text("sk-ant-x")
    system = FakeVm()
    system.active.add("data-director.target")
    assert apply(system, Place.vm(vm), vm) == 0
    profile = (vm.etc / "profile.yaml").read_text()
    assert "\norchestrator: orchestrator.model\n" in profile
    assert f"\nversion: {example_version() + 2}\n" in profile
    wants = (vm.unit_dir / "data-director.target.d" / "agents.conf").read_text()
    assert "Wants=data-director-agent@orchestrator-model.service" in wants
    app = (vm.unit_dir / "data-director-app.service.d" / "agents.conf").read_text()
    assert 'DD_WAIT_PORTS=8101 8106 8107"' in app
    assert ("systemctl", "daemon-reload") in system.calls
    assert ("systemctl", "restart", "data-director.target") in system.calls
    assert any(call[0] == "env" for call in system.calls)  # credentials drop-ins rewritten


def with_documentation(vm: Vm) -> None:
    """The release also lists the Documentation Editor, whose model is on by default."""
    listed = vm.current / "app" / "config" / "agents.yaml"
    listed.write_text(AGENTS + "  - name: advisor-documentation\n    url: http://127.0.0.1:8114/\n")


def test_the_documentation_editor_with_no_key_is_refused_until_it_has_one_or_is_turned_off(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    with_documentation(vm)
    assert apply(FakeVm(), Place.vm(vm), vm) == 1
    out = capsys.readouterr().out
    assert says(out, "refused", "secret set advisor-documentation anthropic-api-key")
    assert says(out, "refused", "DD_DOCUMENTATION_WRITER=template")

    settings = vm.agent_env("advisor-documentation")
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("DD_DOCUMENTATION_WRITER=template\n")
    assert apply(FakeVm(), Place.vm(vm), vm) == 0


def test_the_policy_advisor_with_no_key_is_refused_until_it_has_one_or_is_turned_off(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    listed = vm.current / "app" / "config" / "agents.yaml"
    listed.write_text(AGENTS + "  - name: advisor-policy\n    url: http://127.0.0.1:8108/\n")
    assert apply(FakeVm(), Place.vm(vm), vm) == 1
    out = capsys.readouterr().out
    assert says(out, "refused", "secret set advisor-policy anthropic-api-key")
    assert says(out, "refused", "DD_POLICY_ADVISOR=template")

    settings = vm.agent_env("advisor-policy")
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("DD_POLICY_ADVISOR=template\n")
    assert apply(FakeVm(), Place.vm(vm), vm) == 0


def test_the_policy_advisor_without_an_open_policy_finder_key_is_noted_with_the_secret_command(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    listed = vm.current / "app" / "config" / "agents.yaml"
    listed.write_text(AGENTS + "  - name: advisor-policy\n    url: http://127.0.0.1:8108/\n")
    settings = vm.agent_env("advisor-policy")
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("DD_POLICY_ADVISOR=template\n")
    system = FakeVm()
    system.units["data-director-agent@advisor-policy.service"] = {
        "ActiveState": "active",
        "UnitFileState": "enabled",
        "NRestarts": "0",
    }
    _, out = check(system, vm, capsys)
    assert says(out, "note", "OPEN_POLICY_FINDER_API_KEY", "open-policy-finder-api-key")

    dropin = vm.credentials_dropin("advisor-policy")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text("[Service]\nLoadCredential=open-policy-finder-api-key:/etc/x\n")
    _, out = check(system, vm, capsys)
    assert not says(out, "note", "OPEN_POLICY_FINDER_API_KEY")


def test_the_documentation_editor_on_by_default_with_no_key_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    with_documentation(vm)
    system = FakeVm(answering={8101, 8106, 8114})
    system.units["data-director-agent@advisor-documentation.service"] = {
        "ActiveState": "failed",
        "UnitFileState": "enabled",
        "NRestarts": "3",
    }
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "fix", "data-director secret set advisor-documentation anthropic-api-key")


def test_a_disabled_agent_leaves_the_profile_and_its_running_unit_is_stopped(vm: Vm) -> None:
    (vm.etc / "deployment.yaml").write_text(
        "name: test\norchestrator: stub\ndisabled: [example-hello]\n"
    )
    system = FakeVm()
    system.active.add("data-director-agent@example-hello.service")
    assert apply(system, Place.vm(vm), vm) == 0
    assert "example.hello" not in (vm.etc / "profile.yaml").read_text()
    wants = (vm.unit_dir / "data-director.target.d" / "agents.conf").read_text()
    assert "example-hello" not in wants
    assert (
        "systemctl",
        "disable",
        "--now",
        "data-director-agent@example-hello.service",
    ) in system.calls


def test_apply_on_a_vm_needs_root(vm: Vm) -> None:
    (vm.etc / "deployment.yaml").write_text("name: other\norchestrator: stub\n")
    with pytest.raises(DevError, match="run it as root"):
        apply(FakeVm(root=False), Place.vm(vm), vm)


def test_doctor_reports_a_deployment_not_yet_applied(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    (vm.etc / "deployment.yaml").write_text("name: renamed\norchestrator: stub\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "deployment.yaml")
    assert says(out, "fix", "data-director apply")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: x\norchestrator: clever\n", "orchestrator is model or stub"),
        ("name: x\nprivacy_notice: http://example.ac.uk/p\n", "privacy_notice is the address"),
        ("name: x\nprivacy_notice: javascript:alert(1)\n", "privacy_notice is the address"),
        ("name: x\nprivacy_notice: [https://example.ac.uk/p]\n", "privacy_notice is the address"),
        ("name: x\nmodel_accounts: required\n", "model_accounts is a mapping"),
        ("name: x\ncolour: blue\n", "unknown key colour"),
        ("name: Not A Name\n", "lower-case words"),
        ("name: x\ndisabled: [advisor-nobody]\n", "advisor-nobody, not in agents.yaml"),
        ("name: x\ndisabled: [orchestrator-stub]\n", "the orchestrator, orchestrator-stub"),
    ],
)
def test_a_deployment_that_cannot_be_is_refused_with_why(vm: Vm, text: str, message: str) -> None:
    (vm.etc / "deployment.yaml").write_text(text)
    with pytest.raises(DevError, match=message):
        plan(FakeVm(), Place.vm(vm), vm)


def test_model_accounts_in_the_deployment_reach_the_profile_and_raise_its_version(vm: Vm) -> None:
    import yaml

    before = yaml.safe_load((vm.etc / "profile.yaml").read_text())
    assert "model_accounts" not in before  # unset: the deployment pays
    (vm.etc / "deployment.yaml").write_text(
        "name: test\norchestrator: stub\nmodel_accounts:\n  own: allowed\n"
        "  fallback: deployment\n  providers:\n    - provider: anthropic\n"
    )
    assert apply(FakeVm(), Place.vm(vm), vm) == 0
    after = yaml.safe_load((vm.etc / "profile.yaml").read_text())
    assert after["model_accounts"]["own"] == "allowed"
    assert after["version"] > before["version"]


def test_no_backup_timer_and_a_failed_backup_are_problems(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.active.discard("data-director-backup.timer")
    system.units["data-director-backup.service"] = {"Result": "exit-code"}
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", "data-director-backup.timer")
    assert says(out, "problem", "exit-code")
    assert says(out, "fix", "journalctl -u data-director-backup.service")


def test_an_old_backup_or_none_names_the_backup_command(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.rmtree(vm.backups)
    make_backup(vm, age=timedelta(days=3))
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "newest backup", "3 days")
    assert says(out, "fix", "data-director backup")
    shutil.rmtree(vm.backups)
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "no backup", str(vm.backups))


def test_backups_kept_where_backup_env_says_are_found(
    vm: Vm, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    elsewhere = tmp_path / "elsewhere"
    vm.backup_env.write_text(f"DD_BACKUP_DIR={elsewhere}\n")
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1 and says(out, "problem", "no backup", str(elsewhere))
    (elsewhere / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")).mkdir(parents=True)
    status, out = check(FakeVm(), vm, capsys)
    assert status == 0, out


def test_a_full_disk_is_a_problem(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    status, out = check(FakeVm(free=(100 * 2**30, 2**30)), vm, capsys)
    assert status == 1
    assert says(out, "problem", str(vm.state), "free")
    assert says(out, "problem", str(vm.backups), "free")


def test_no_room_for_another_backup_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(FakeVm(free=(1000, 200)), vm, capsys)
    assert status == 1
    assert says(out, "problem", str(vm.backups), "less than the last backup")


def test_a_database_store_with_another_schema_names_the_migration(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    location = "postgresql://dd@/dd"
    harness = vm.current / ".venv" / "bin" / "dd-harness"
    harness.parent.mkdir(parents=True)
    harness.write_text("")
    vm.app_env.write_text(
        vm.app_env.read_text()
        + f"DD_RUNS_DIR={location}\nDD_PROJECTS_DIR={location}\nPGHOST=/run/postgresql\n"
    )
    system = FakeVm()
    status, out = check(system, vm, capsys)
    assert status == 0, out
    [asked] = [call for call in system.calls if "storage" in call]
    assert "PGHOST=/run/postgresql" in asked and asked[-1] == location

    system = FakeVm(schema=Done(1, f"{location}: version 2, this build expects 3"))
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", location, "version 2")
    assert says(out, "fix", "storage migrate")


def test_the_report_as_json_has_each_problem_with_its_fix(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.about = {**(system.about or {}), "commit": "c" * 40}
    status = Doctor(system, vm).run(as_json=True)
    report = json.loads(capsys.readouterr().out)
    assert status == 1
    assert report["target"]["kind"] == "vm"
    assert report["target"]["release"] == SHA
    assert any(
        "cccccccccc" in problem["text"] and "--bootstrap" in (problem["fix"] or "")
        for problem in report["problems"]
    )
    assert isinstance(report["notes"], list) and isinstance(report["skipped"], list)


def test_a_healthy_vm_as_json_has_no_problems(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    assert Doctor(FakeVm(), vm).run(as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["problems"] == []


def test_an_admin_service_that_is_not_running_is_a_problem(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    system.active.discard("data-director-admin.service")
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", "data-director-admin.service")
    assert says(out, "fix", "enable --now data-director-admin.service")


def test_the_apps_model_grant_secrets_make_apply_sync_the_credentials(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = FakeVm()
    assert apply(system, Place.vm(vm), vm) == 0
    capsys.readouterr()
    app = vm.credentials / "app"
    app.mkdir(parents=True, exist_ok=True)
    for name in ("model-grant-signing-key", "model-broker-subject-key", "pseudonym-secret"):
        (app / name).write_text("x")
    dropin = vm.unit_dir / "data-director-app.service.d" / "model-grants.conf"

    # With the files in place and no drop-in yet, apply has something to do, and runs the sync.
    system = FakeVm()
    assert apply(system, Place.vm(vm), vm, check=True) == 1
    assert f"would change: {dropin}" in capsys.readouterr().out
    assert apply(system, Place.vm(vm), vm) == 0
    assert any(
        call[0] == "env" and "sync_all_credentials" in " ".join(call) for call in system.calls
    )

    # Once the drop-in loads them all, there is nothing to change.
    dropin.write_text(
        "[Service]\n"
        + "".join(
            f"LoadCredential={name}:{app / name}\n"
            for name in ("model-grant-signing-key", "model-broker-subject-key", "pseudonym-secret")
        )
    )
    capsys.readouterr()
    assert apply(FakeVm(), Place.vm(vm), vm, check=True) == 0
    assert "Nothing to change." in capsys.readouterr().out


# An agent that calls through the model broker needs its broker credential and no provider key
# in place of a key (scripts/ddtool/model_access.py).
BROKERED = "DD_MODEL_BROKER_URL=http://127.0.0.1:8300\n"


def model_orchestrator(vm: Vm, settings: str, *secrets: str) -> FakeVm:
    """The model orchestrator turned on, with these settings and secrets, as `apply` leaves it."""
    (vm.etc / "deployment.yaml").write_text("name: test\norchestrator: model\n")
    own = vm.agent_env("orchestrator-model")
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_text(settings)
    (vm.credentials / "orchestrator-model").mkdir()
    for secret in secrets:
        (vm.credentials / "orchestrator-model" / secret).write_text("x")
    dropin = vm.credentials_dropin("orchestrator-model")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text("[Service]\n" + "".join(f"LoadCredential={s}:/etc/x\n" for s in secrets))
    system = FakeVm(answering={8101, 8106, 8107})
    system.units["data-director-agent@orchestrator-model.service"] = {
        "ActiveState": "active",
        "UnitFileState": "enabled",
        "NRestarts": "0",
    }
    return system


@pytest.mark.parametrize("root", [True, False])
def test_a_brokered_agent_with_its_credential_and_no_key_is_all_good(
    vm: Vm, capsys: pytest.CaptureFixture[str], root: bool
) -> None:
    system = model_orchestrator(vm, BROKERED, "dd-model-broker-credential")
    assert apply(system, Place.vm(vm), vm) == 0, capsys.readouterr().out
    system.root = root
    status, out = check(system, vm, capsys)
    assert status == 0, out


def test_the_broker_url_in_the_shared_settings_counts(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = model_orchestrator(vm, "", "dd-model-broker-credential")
    vm.agents_env.write_text(BROKERED)
    assert apply(system, Place.vm(vm), vm) == 0, capsys.readouterr().out
    status, out = check(system, vm, capsys)
    assert status == 0, out


def test_a_brokered_agent_that_also_holds_a_key_is_told_to_remove_it(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = model_orchestrator(vm, BROKERED, "dd-model-broker-credential", "anthropic-api-key")
    assert apply(system, Place.vm(vm), vm) == 1
    assert says(capsys.readouterr().out, "refused", "secret remove orchestrator-model")
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "fix", "data-director secret remove orchestrator-model anthropic-api-key")
    assert not says(out, "fix", "secret set orchestrator-model")


def test_a_brokered_agent_without_its_credential_names_the_broker_script(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = model_orchestrator(vm, BROKERED)
    assert apply(system, Place.vm(vm), vm) == 1
    assert says(capsys.readouterr().out, "refused", "deploy/broker-credentials.sh")
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "fix", "deploy/broker-credentials.sh")
    assert not says(out, "fix", "secret set orchestrator-model anthropic-api-key")
