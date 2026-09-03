"""Ranking weights, loaded from a versioned file (§5.3).

The weights live in a configuration file with a version number, recorded with every run. §5.3's
reason is worth restating because it shapes the loader: it makes a change to the ranking "a
visible, attributed, repeatable event", and it lets a test harness sweep weight combinations
against fixtures instead of anyone tuning by instinct.

The version is the filename stem, so a new weighting is a new file rather than an edit — the
same discipline the prompt library enforces, for the same reason.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from standards_advisor.errors import ConfigError
from standards_advisor.ids import sha256_text
from standards_advisor.models.common import RankingConfigRef


@dataclass(frozen=True)
class RankingConfig:
    version: str
    confidence_floor: float
    weights: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    sha256: str = ""

    def ref(self) -> RankingConfigRef:
        return RankingConfigRef(version=self.version, sha256=self.sha256)

    def weight(self, rule_name: str) -> float:
        """The weight for a rule, or zero.

        Zero rather than an error: a rule present in code but absent from an older weights file
        should contribute nothing to that run, not break it. Which is different from a rule
        being *skipped* — see `ranking.rules`.
        """
        return self.weights.get(rule_name, 0.0)


def load_ranking_config(path: Path) -> RankingConfig:
    """Load and validate a weights file."""
    if not path.is_file():
        raise ConfigError(f"ranking configuration not found at {path}")

    text = path.read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"ranking configuration at {path} is not valid TOML: {exc}") from exc

    version = str(raw.get("version") or path.stem)
    if version != path.stem:
        raise ConfigError(
            f"ranking configuration at {path} declares version {version!r} but its filename "
            f"says {path.stem!r}; the filename is the version"
        )

    floor = raw.get("confidence_floor")
    if not isinstance(floor, int | float):
        raise ConfigError(f"ranking configuration at {path} has no numeric confidence_floor")
    if not 0.0 <= float(floor) <= 1.0:
        raise ConfigError(f"confidence_floor in {path} must be between 0 and 1, got {floor}")

    return RankingConfig(
        version=version,
        confidence_floor=float(floor),
        weights=_numeric_table(raw.get("weights"), path, "weights"),
        penalties=_numeric_table(raw.get("penalties"), path, "penalties"),
        sha256=sha256_text(text),
    )


def _numeric_table(value: object, path: Path, label: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"[{label}] in {path} must be a table")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(item, int | float):
            raise ConfigError(f"{label}.{key} in {path} must be a number, got {item!r}")
        result[str(key)] = float(item)
    return result
