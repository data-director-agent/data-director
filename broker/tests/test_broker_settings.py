"""A missing or malformed setting stops the broker at start-up in one line that names the setting
and never the secret (docs/specs/model-accounts.md, invariant 8)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from joserfc.jwk import ECKey

from dd_broker import cli
from dd_broker.agents import digest
from dd_broker.settings import BrokerSettings, SettingsError

SECRET_CREDENTIAL = "dd-broker-settings-test-credential-77aa"


def environment(tmp_path: Path) -> dict[str, str]:
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "kek").write_text(base64.b64encode(os.urandom(32)).decode())
    (credentials / "subject").write_text(ECKey.generate_key("P-256").as_pem(private=True).decode())
    (credentials / "agents").write_text(
        json.dumps({"advisor.standards": digest(SECRET_CREDENTIAL)})
    )
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": []}))
    return {
        "CREDENTIALS_DIRECTORY": str(credentials),
        "DD_BROKER_KEY_ENCRYPTION_KEY_FILE": "kek",
        "DD_BROKER_SUBJECT_KEY_FILE": "subject",
        "DD_BROKER_AGENT_CREDENTIALS_FILE": "agents",
        "DD_BROKER_HARNESS_JWKS_FILE": str(jwks),
        "DD_BROKER_STORE": str(tmp_path / "broker.sqlite3"),
    }


def test_a_complete_environment_is_read(tmp_path: Path) -> None:
    settings = BrokerSettings.from_env(
        environment(tmp_path)
        | {
            "ANTHROPIC_API_KEY": "sk-gateway-virtual-key",
            "DD_BROKER_DEPLOYMENT_BASE_URL": "http://127.0.0.1:4000/",
            "DD_BROKER_ALLOWED_BASE_URLS": "https://models.example.ac.uk, https://b.example",
        }
    )
    assert settings.agents.authenticate(SECRET_CREDENTIAL) == "advisor.standards"
    assert settings.deployment_base_url == "http://127.0.0.1:4000"
    assert settings.allowed_base_urls == ("https://models.example.ac.uk", "https://b.example")
    assert "sk-gateway-virtual-key" not in repr(settings)


def test_the_deployment_key_is_optional(tmp_path: Path) -> None:
    assert BrokerSettings.from_env(environment(tmp_path)).deployment_key is None


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"DD_BROKER_KEY_ENCRYPTION_KEY_FILE": ""}, "DD_BROKER_KEY_ENCRYPTION_KEY"),
        ({"DD_BROKER_KEY_ENCRYPTION_KEY": "c2hvcnQ="}, "DD_BROKER_KEY_ENCRYPTION_KEY"),
        ({"DD_BROKER_SUBJECT_KEY_FILE": "agents"}, "DD_BROKER_SUBJECT_KEY"),
        ({"DD_BROKER_AGENT_CREDENTIALS_FILE": "kek"}, "DD_BROKER_AGENT_CREDENTIALS"),
        ({"DD_BROKER_HARNESS_JWKS_FILE": ""}, "DD_BROKER_HARNESS_JWKS"),
        ({"DD_BROKER_HARNESS_JWKS_URL": "https://h.example/jwks"}, "DD_BROKER_HARNESS_JWKS"),
        ({"DD_BROKER_STORE": ""}, "DD_BROKER_STORE"),
        ({"DD_BROKER_ALLOWED_BASE_URLS": "http://plain.example"}, "DD_BROKER_ALLOWED_BASE_URLS"),
        ({"DD_BROKER_DEPLOYMENT_BASE_URL": "file:///etc"}, "DD_BROKER_DEPLOYMENT_BASE_URL"),
    ],
)
def test_a_bad_setting_is_named_and_no_secret_is_shown(
    tmp_path: Path, change: dict[str, str], named: str
) -> None:
    env = environment(tmp_path)
    if change.get("DD_BROKER_KEY_ENCRYPTION_KEY"):
        env.pop("DD_BROKER_KEY_ENCRYPTION_KEY_FILE")
    env |= change
    with pytest.raises(SettingsError) as caught:
        BrokerSettings.from_env({k: v for k, v in env.items() if v})
    message = str(caught.value)
    assert named in message
    assert "\n" not in message
    credentials = Path(env["CREDENTIALS_DIRECTORY"])
    for secret_file in credentials.iterdir():
        assert secret_file.read_text().strip() not in message
    assert SECRET_CREDENTIAL not in message


def test_serve_stops_in_one_line_on_a_bad_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in list(os.environ):
        if name.startswith("DD_BROKER_"):
            monkeypatch.delenv(name)
    with pytest.raises(SystemExit) as caught:
        cli.main(["serve"])
    assert str(caught.value).startswith("dd-model-broker: ")
    assert "\n" not in str(caught.value)
