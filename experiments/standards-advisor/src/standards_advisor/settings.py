"""Settings, read from the environment with explicit defaults.

Plain `os.environ` reads rather than `pydantic-settings`: there are six values, and a dependency
whose whole job is reading six environment variables is not worth a maintainer's review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from standards_advisor.errors import ConfigError
from standards_advisor.llm.provider import DEFAULT_MODEL_ID

DEFAULT_AGENT_IDENTITY = "urn:dd:agent:sheffield-r3"
DEFAULT_HEAD_ROWS = 500
DEFAULT_REGISTRY_ROUTE = "empty"
DEFAULT_RANKING_CONFIG = "ranking.v1"
DEFAULT_INTAKE_CONFIG = "intake.v1"


@dataclass(frozen=True)
class Settings:
    """Everything configurable, resolved."""

    project_root: Path
    runs_root: Path
    model_id: str
    agent_identity: str
    head_rows: int
    registry_route: str
    ranking_config: str
    intake_config: str

    @property
    def prompts_root(self) -> Path:
        return self.project_root / "prompts"

    @property
    def config_root(self) -> Path:
        return self.project_root / "config"

    @property
    def schemas_root(self) -> Path:
        return self.project_root / "schemas"

    def ranking_config_path(self) -> Path:
        return self.config_root / f"{self.ranking_config}.toml"

    def intake_config_path(self) -> Path:
        return self.config_root / f"{self.intake_config}.toml"


def find_project_root(start: Path | None = None) -> Path:
    """Walk upwards for the directory holding `pyproject.toml`.

    The prompts, weights and schemas live beside the package rather than inside it, because they
    are meant to be read and reviewed as files. That makes locating the project root part of
    normal operation rather than a packaging afterthought.
    """
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ConfigError(
        "could not locate the experiment root (no pyproject.toml found above "
        f"{current}); pass --project-root"
    )


def load_settings(
    environ: dict[str, str],
    *,
    project_root: Path | None = None,
    runs_root: Path | None = None,
) -> Settings:
    root = project_root or find_project_root()
    return Settings(
        project_root=root,
        runs_root=runs_root or (root / "runs"),
        model_id=environ.get("DD_MODEL_ID") or DEFAULT_MODEL_ID,
        agent_identity=environ.get("DD_AGENT_IDENTITY") or DEFAULT_AGENT_IDENTITY,
        head_rows=_positive_int(environ.get("DD_HEAD_ROWS"), DEFAULT_HEAD_ROWS, "DD_HEAD_ROWS"),
        registry_route=environ.get("DD_REGISTRY_ROUTE") or DEFAULT_REGISTRY_ROUTE,
        ranking_config=environ.get("DD_RANKING_CONFIG") or DEFAULT_RANKING_CONFIG,
        intake_config=environ.get("DD_INTAKE_CONFIG") or DEFAULT_INTAKE_CONFIG,
    )


def _positive_int(raw: str | None, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value
