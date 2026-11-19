"""The roster's states, checked across every in-tree agent (docs/specs/agents.md, invariants 13
and 14).

Each agent's own tests check its own "Mock." prefix, or its absence. This module checks the rest of
the two rules for the whole roster at once, from the cards themselves: that every in-tree agent is
placed in one state by the roster table in the spec, that a mock and a model-backed alpha each have what their rule asks, that an
alpha's `template` path declares no model, and that the tests of a mock or an alpha substantiate
no Blueprint requirement. Whether an outcome statement states a `Document` payload's limitations
is prose, and is not checked here.
"""

from __future__ import annotations

import ast
import functools
import importlib
import re
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
SPEC = ROOT / "docs" / "specs" / "agents.md"

MOCK, ALPHA, PERSONA, BY_DESIGN = "mock", "alpha", "persona", "by design"

# The first words of each row of the roster table in docs/specs/agents.md, and the state it gives.
STATES: Mapping[str, str] = {
    "Mock": MOCK,
    "Model-backed alpha": ALPHA,
    "Persona": PERSONA,
    "Deterministic by design": BY_DESIGN,
}
ROW = re.compile(rf"^\| ({'|'.join(STATES)})\b[^|]*\|([^|]*)\|$", re.MULTILINE)


def _roster(spec: str) -> dict[str, str]:
    """Every in-tree agent's state, as the roster table in the spec gives it. The table is the one
    place a state is written down, so that a new agent's state is a decision and not an accident."""
    roster: dict[str, str] = {}
    for label, cell in ROW.findall(spec):
        for agent_id in re.findall(r"`([\w.]+)`", cell):
            assert agent_id not in roster, f"{agent_id}: in more than one row of the roster table"
            roster[agent_id] = STATES[label]
    return roster


ROSTER: Mapping[str, str] = _roster(SPEC.read_text(encoding="utf-8"))

# Blueprint requirements a mock's or an alpha's tests still name, by agent. The list only shrinks:
# an entry that no longer occurs fails too.
KNOWN_EXCEPTIONS: Mapping[str, frozenset[str]] = {
    # TODO(#967): the Documentation Editor substantiates R5 while it is an alpha; it leaves alpha
    # on its evaluation set, or its tests drop the mark.
    "advisor.documentation": frozenset({"R5"}),
}


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


def _assert_states_limitations(spec: AgentSpec) -> None:
    """The payload has a `limitations` slot, or is the core `Document`, whose outcome statement
    says them instead."""
    assert spec.payload is not None, f"{spec.agent_id}: an advisor with no payload"
    assert spec.payload.name == "Document" or "limitations" in spec.payload.json_schema.get(
        "properties", {}
    ), f"{spec.agent_id}: its payload does not state its limitations"


@functools.cache
def _blueprint() -> frozenset[str]:
    """The ids of the register's Blueprint requirements."""
    register = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    return frozenset(e["id"] for e in register["requirements"] if e.get("source") == "blueprint")


def _blueprint_marks(package: Path) -> set[str]:
    """The Blueprint requirement ids that `pytest.mark.requirement(...)` names in the package's
    tests, whether on a test or as `pytestmark`."""
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
    return named & _blueprint()


def test_the_roster_table_gives_every_state() -> None:
    assert set(ROSTER.values()) == set(STATES.values())


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
    _assert_states_limitations(spec)
    assert spec.models == ()


@pytest.mark.requirement("DD-GROUNDING-MODE")
@pytest.mark.parametrize("agent_id", _in(ALPHA))
def test_a_model_backed_alpha_is_pre_release_grounded_and_states_its_limitations(
    agent_id: str,
) -> None:
    _, spec = SPECS[agent_id]
    assert Version(spec.version).is_prerelease, spec.version
    assert spec.grounding_mode in (GroundingMode.INPUT_ONLY, GroundingMode.RETRIEVAL)
    _assert_states_limitations(spec)


def _factory(agent_id: str) -> tuple[Callable[[Mapping[str, str]], Any], str, str]:
    """The alpha's `build`, the setting that chooses its `template` path, and that setting's
    default, as the package's `factory` module declares them. Only the Documentation Editor's and
    the Policy Adviser's models are on by default (Model-backed personas)."""
    package, _ = SPECS[agent_id]
    factory = importlib.import_module(f"{_module(package)}.factory")
    return factory.build, factory.SWITCH, factory.DEFAULT


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
    assert set(KNOWN_EXCEPTIONS) <= set(_in(MOCK) + _in(ALPHA))
