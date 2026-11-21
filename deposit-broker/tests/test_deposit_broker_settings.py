"""The deposit broker's settings: what it refuses to start with
(docs/guide/operations/deposit-broker.md)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from deposit_broker_support import SANDBOX, kek_b64
from joserfc.jwk import ECKey

from dd_deposit_broker.settings import DepositBrokerSettings, SettingsError


def env(**changes: Any) -> dict[str, str]:
    base = {
        "DD_DEPOSIT_BROKER_KEY_ENCRYPTION_KEY": kek_b64(),
        "DD_DEPOSIT_BROKER_SUBJECT_KEY": json.dumps(
            ECKey.generate_key("P-256").as_dict(private=True)
        ),
        "DD_DEPOSIT_BROKER_HARNESS_JWKS_URL": "http://127.0.0.1:7860/.well-known/jwks.json",
        "DD_DEPOSIT_BROKER_STORE": "/var/lib/data-director/deposit-broker.sqlite",
        "DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS": f"zenodo={SANDBOX}",
    }
    return {k: v for k, v in {**base, **changes}.items() if v is not None}


def test_a_sandbox_deployment_starts() -> None:
    settings = DepositBrokerSettings.from_env(env())
    assert settings.allowed == {SANDBOX: "zenodo"}
    assert settings.oauth_clients == {}
    assert "KEY" not in repr(settings)


def test_oauth_clients_need_the_public_and_app_urls() -> None:
    clients = json.dumps({SANDBOX: {"client_id": "a", "client_secret": "s3cret-0f-the-app"}})
    with pytest.raises(SettingsError, match="PUBLIC_URL"):
        DepositBrokerSettings.from_env(env(DD_DEPOSIT_BROKER_OAUTH_CLIENTS=clients))
    settings = DepositBrokerSettings.from_env(
        env(
            DD_DEPOSIT_BROKER_OAUTH_CLIENTS=clients,
            DD_DEPOSIT_BROKER_PUBLIC_URL="https://dd.test/deposit-broker/",
            DD_DEPOSIT_BROKER_APP_URL="https://dd.test",
        )
    )
    assert settings.public_url == "https://dd.test/deposit-broker"
    assert settings.oauth_clients[SANDBOX].client_id == "a"
    assert "s3cret" not in repr(settings.oauth_clients)


@pytest.mark.parametrize(
    ("changes", "refusal"),
    [
        ({"DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS": None}, "ALLOWED_BASE_URLS"),
        ({"DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS": "zenodo=http://x/api"}, "https URL"),
        ({"DD_DEPOSIT_BROKER_ALLOWED_BASE_URLS": "dropbox=https://x/api"}, "transport"),
        ({"DD_DEPOSIT_BROKER_KEY_ENCRYPTION_KEY": "c2hvcnQ="}, "not 32 bytes"),
        ({"DD_DEPOSIT_BROKER_STORE": None}, "SQLite"),
        ({"DD_DEPOSIT_BROKER_HARNESS_JWKS_URL": None}, "set one of"),
        (
            {
                "DD_DEPOSIT_BROKER_OAUTH_CLIENTS": json.dumps(
                    {"https://zenodo.org/api": {"client_id": "a", "client_secret": "b"}}
                )
            },
            "not in",
        ),
    ],
)
def test_an_unusable_setting_stops_start_up(changes: dict[str, str | None], refusal: str) -> None:
    with pytest.raises(SettingsError, match=refusal):
        DepositBrokerSettings.from_env(env(**changes))
