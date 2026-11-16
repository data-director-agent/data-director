"""The roster's states, checked across every in-tree agent (docs/specs/agents.md, invariants 13
and 14).

Each agent's own tests check its own "Mock." prefix, or its absence. This module checks the rest of
the two rules for the whole roster at once, from the cards themselves: that every in-tree agent is
placed in one state, that a mock and a model-backed alpha each have what their rule asks, that an
alpha's `template` path declares no model, and that the tests of a mock or an alpha substantiate
no Blueprint requirement. Whether an outcome statement states a `Document` payload's limitations
is prose, and is not checked here.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.version import Version

from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import GroundingMode
from dd_sdk.credentials import ConfigError

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "agents"
REGISTER = ROOT / "docs" / "requirements.yaml"

MOCK, ALPHA, PERSONA, BY_DESIGN = "mock", "alpha", "persona", "by design"

# Every in-tree agent's state, as the roster table in docs/specs/agents.md gives it. A new agent
# is added here, so that its state is a decision and not an accident.
ROSTER: Mapping[str, str] = {
    "advisor.dmp": MOCK,
    "advisor.ethics": MOCK,
    "advisor.fairness": MOCK,
    "advisor.files": MOCK,
    "advisor.linking": MOCK,
    "advisor.metadata": MOCK,
    "advisor.rights": MOCK,
    "advisor.documentation": ALPHA,
    "advisor.policy": ALPHA,
    "advisor.quality": PERSONA,
    "advisor.repository": PERSONA,
    "advisor.standards": PERSONA,
    "example.hello": BY_DESIGN,
    "orchestrator.model": BY_DESIGN,
    "orchestrator.stub": BY_DESIGN,
}

# Each model-backed alpha's factory, the setting that chooses its `template` path, and that
# setting's default. Only the Documentation Editor's and the Policy Adviser's models are on by
# default (Model-backed personas).
ALPHA_SWITCHES: Mapping[str, tuple[str, str, str]] = {
    "advisor.documentation": (
        "dd_agent_advisor_documentation.factory",
        "DD_DOCUMENTATION_WRITER",
        "model",
    ),
    "advisor.policy": ("dd_agent_advisor_policy.factory", "DD_POLICY_ADVISOR", "model"),
}

# Blueprint requirements a mock's or an alpha's tests still name, by agent. The list only shrinks:
# an entry that no longer occurs fails too.
KNOWN_EXCEPTIONS: Mapping[str, frozenset[str]] = {
    # TODO(#967): the Documentation Editor substantiates R5 while it is an alpha; it leaves alpha
    # on its evaluation set, or its tests drop the mark.
    "advisor.documentation": frozenset({"R5"}),
}

# Mocks and alphas whose payload does not yet say what they do not do. The list only shrinks too.
NO_LIMITATIONS: frozenset[str] = frozenset(
    {
        # TODO(#968): the Policy Adviser's `PolicyChecks` has no `limitations` slot.
        "advisor.policy",
    }
)


def _module(package: Path) -> str:
    """The one import package under the agent's `src/`."""
    (module,) = (p.name for p in (package / "src").iterdir() if (p / "__init__.py").is_file())
    return module


def _spec(package: Path) -> AgentSpec:
    """The one spec the package's `agent` module declares as a class attribute."""
    module = importlib.import_module(f"{_module(package)}.agent")
    specs = [
        spec
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__
        for spec in [getattr(value, "spec", None)]
        if isinstance(spec, AgentSpec)
    ]
    assert len(specs) == 1, f"{package.name}: expected one agent class, found {len(specs)}"
    return specs[0]


PACKAGES = sorted(p for p in AGENTS.iterdir() if (p / "pyproject.toml").is_file())
SPECS: dict[str, tuple[Path, AgentSpec]] = {
    spec.agent_id: (package, spec) for package in PACKAGES for spec in [_spec(package)]
}


def _in(state: str) -> list[str]:
    return sorted(agent_id for agent_id, s in ROSTER.items() if s == state)


def _states_limitations(spec: AgentSpec) -> bool:
    """The payload has a `limitations` slot, or is the core `Document`, whose outcome statement
    says them instead."""
    assert spec.payload is not None, f"{spec.agent_id}: an advisor with no payload"
    return spec.payload.name == "Document" or "limitations" in spec.payload.json_schema.get(
        "properties", {}
    )


def _blueprint_marks(package: Path) -> set[str]:
    """The Blueprint requirement ids that `pytest.mark.requirement(...)` names in the package's
    tests, whether on a test or as `pytestmark`."""
    register = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    blueprint = {e["id"] for e in register["requirements"] if e.get("source") == "blueprint"}
    named: set[str] = set()
    for path in (package / "tests").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "requirement"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "mark"
            ):
                named |= {
                    a.value
                    for a in node.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                }
    return named & blueprint


@pytest.mark.requirement("DD-REGISTRY")
def test_every_in_tree_agent_has_a_state_in_the_roster() -> None:
    assert set(SPECS) == set(ROSTER)


@pytest.mark.requirement("DD-REGISTRY")
@pytest.mark.parametrize("agent_id", sorted(ROSTER))
def test_only_a_mock_says_it_is_a_mock(agent_id: str) -> None:
    _, spec = SPECS[agent_id]
    assert spec.description.startswith("Mock.") == (ROSTER[agent_id] == MOCK)


@pytest.mark.requirement("DD-GROUNDING-MODE")
@pytest.mark.parametrize("agent_id", _in(MOCK))
def test_a_mock_is_ungrounded_and_states_its_limitations(agent_id: str) -> None:
    _, spec = SPECS[agent_id]
    assert spec.grounding_mode is GroundingMode.NONE
    assert _states_limitations(spec) == (agent_id not in NO_LIMITATIONS)
    assert spec.models == ()


@pytest.mark.requirement("DD-GROUNDING-MODE")
@pytest.mark.parametrize("agent_id", _in(ALPHA))
def test_a_model_backed_alpha_is_pre_release_grounded_and_states_its_limitations(
    agent_id: str,
) -> None:
    _, spec = SPECS[agent_id]
    assert Version(spec.version).is_prerelease, spec.version
    assert spec.grounding_mode in (GroundingMode.INPUT_ONLY, GroundingMode.RETRIEVAL)
    assert _states_limitations(spec) == (agent_id not in NO_LIMITATIONS)


def test_every_alpha_names_the_switch_to_its_template_path() -> None:
    assert set(ALPHA_SWITCHES) == set(_in(ALPHA))


def _factory(agent_id: str) -> tuple[Callable[[Mapping[str, str]], Any], str, str]:
    module, switch, default = ALPHA_SWITCHES[agent_id]
    return importlib.import_module(module).build, switch, default


@pytest.mark.requirement("DD-REGISTRY")
@pytest.mark.parametrize("agent_id", _in(ALPHA))
def test_an_alphas_template_path_runs_with_no_key_and_declares_no_model(agent_id: str) -> None:
    build, switch, _ = _factory(agent_id)
    agent = build({switch: "template"})
    assert agent.spec.agent_id == agent_id
    assert agent.spec.models == ()


@pytest.mark.parametrize("agent_id", _in(ALPHA))
def test_an_alphas_default_is_template_unless_its_model_is_on_by_default(agent_id: str) -> None:
    build, _, default = _factory(agent_id)
    if default == "template":
        assert build({}).spec.models == ()
    else:
        # On by default, it needs a model configured, and says how to run without one.
        with pytest.raises(ConfigError, match="template"):
            build({})


@pytest.mark.parametrize("agent_id", _in(MOCK) + _in(ALPHA))
def test_a_mock_or_an_alpha_substantiates_no_blueprint_requirement(agent_id: str) -> None:
    package, _ = SPECS[agent_id]
    assert _blueprint_marks(package) == KNOWN_EXCEPTIONS.get(agent_id, frozenset())


def test_every_known_exception_is_a_mock_or_an_alpha() -> None:
    assert set(KNOWN_EXCEPTIONS) | NO_LIMITATIONS <= set(_in(MOCK) + _in(ALPHA))
