"""Model credentials are read once, explicitly, and never echoed (ADR-0026)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_sdk import serve
from dd_sdk.agent import Agent
from dd_sdk.credentials import ConfigError, api_key

KEY = "sk-ant-test-0123456789"


def test_the_variable_gives_the_key() -> None:
    assert api_key({"ANTHROPIC_API_KEY": f" {KEY}\n"}) == KEY


def test_an_absolute_file_gives_the_key(tmp_path: Path) -> None:
    (tmp_path / "key").write_text(KEY + "\n")
    assert api_key({"ANTHROPIC_API_KEY_FILE": str(tmp_path / "key")}) == KEY


def test_a_relative_file_is_found_in_the_credentials_directory(tmp_path: Path) -> None:
    (tmp_path / "anthropic-api-key").write_text(KEY)
    env = {"ANTHROPIC_API_KEY_FILE": "anthropic-api-key", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    assert api_key(env) == KEY


def test_another_provider_uses_its_own_name() -> None:
    assert api_key({"OTHER_API_KEY": KEY}, name="OTHER_API_KEY") == KEY


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "no model key"),
        ({"ANTHROPIC_API_KEY": ""}, "no model key"),
        ({"ANTHROPIC_API_KEY": " \n"}, "no model key"),
        ({"ANTHROPIC_API_KEY": KEY, "ANTHROPIC_API_KEY_FILE": "/k"}, "not both"),
        ({"ANTHROPIC_API_KEY_FILE": "k"}, "CREDENTIALS_DIRECTORY is not set"),
        ({"ANTHROPIC_API_KEY_FILE": "/nonexistent/k"}, "cannot read"),
    ],
)
def test_an_unusable_configuration_is_one_error(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message) as caught:
        api_key(env)
    assert KEY not in str(caught.value)


def test_an_empty_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "key").write_text("\n")
    with pytest.raises(ConfigError, match="empty"):
        api_key({"ANTHROPIC_API_KEY_FILE": str(tmp_path / "key")})


def test_serve_reports_a_configuration_error_in_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def build() -> Agent:
        raise ConfigError("no model key: set ANTHROPIC_API_KEY")

    assert serve.main(build, ["serve"]) == serve.EXIT_CONFIG
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "no model key" in err
