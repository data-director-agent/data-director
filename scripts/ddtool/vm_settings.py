"""The checks of `dd.py doctor` on a VM that read what the operator configured: the agents' model
keys and secrets, the app's and agents' settings files, the profile, and whether the instance is
what deployment.yaml says."""

from __future__ import annotations

from pathlib import Path

from ddtool.common import (
    KEY_VARS,
    MODEL_BACKED,
    MODEL_BY_DEFAULT,
    PROVIDER_KEYS,
    Agent,
    DevError,
    compare_profile,
)
from ddtool.deployment import Place, plan
from ddtool.vm import agent_unit, loaded_secrets, read_settings, systemctl_show, wanted_agents
from ddtool.vm_report import Checks

# The settings the app needs to sign people in (deploy/install.sh waits for them).
SIGN_IN_SETTINGS = ("DD_OIDC_ISSUER", "DD_OIDC_CLIENT_ID", "DD_APP_PUBLIC_URL")
OPERATOR_SETTINGS = ("DD_PRINCIPAL_ID", "DD_PRINCIPAL_NAME")
MODEL_KEY = "anthropic-api-key"
# The agents a model only helps, by the setting that turns their model on.
MODEL_SWITCHES = {
    "advisor-standards": "DD_STANDARDS_EXPLAINER",
    "advisor-policy": "DD_POLICY_ADVISOR",
    "advisor-repository": "DD_REPOSITORY_EXPLAINER",
    "advisor-documentation": "DD_DOCUMENTATION_WRITER",
    "advisor-dmp": "DD_DMP_MATCHER",
    "advisor-rights": "DD_RIGHTS_INTERPRETER",
    "advisor-fairness": "DD_FAIRNESS_WRITER",
}


class SettingsChecks(Checks):
    """Secrets and settings: what the operator set, checked against what the VM runs."""

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
            provider = own.get("DD_MODEL_PROVIDER") or "anthropic"
            needs = (
                agent.name in MODEL_BACKED
                or own.get(
                    MODEL_SWITCHES.get(agent.name, ""),
                    "model" if agent.name in MODEL_BY_DEFAULT else "template",
                )
                in ("model", "anthropic")
                # A local OpenAI-compatible endpoint may need no key; the agent says at start-up.
            ) and provider != "openai-compatible"
            # The secret's name gives the variable the agent reads it from (deploy/credentials.sh).
            secret = (
                PROVIDER_KEYS.get(provider, PROVIDER_KEYS["anthropic"]).lower().replace("_", "-")
            )
            if (
                on
                and needs
                and secret not in loaded_secrets(system, vm, agent.name)
                and not any(own.get(var) for var in KEY_VARS)
            ):
                report.problem(
                    f"{agent.name} calls a model but has no key",
                    f"{self.tool} secret set {agent.name} {secret}",
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
        self._shared_settings()
        try:
            app = read_settings(system, vm.app_env)
        except DevError as exc:
            report.problem(str(exc))
            return
        if app is None:
            report.skip(str(vm.app_env))
            return
        self._app_settings(app)
        self._profile(app, release)

    def _shared_settings(self) -> None:
        """agents.env, which every agent reads, holds no model key."""
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

    def _app_settings(self, app: dict[str, str]) -> None:
        """app.env signs people in, names no operator and holds no model key; the ORCID client
        secret is in place."""
        system, vm, report = self.system, self.vm, self.report
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

    def _profile(self, app: dict[str, str], release: Path | None) -> None:
        """The profile DD_PROFILE names can be read, compared with the release's example."""
        system, report = self.system, self.report
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
