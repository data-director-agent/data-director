"""Where the browser reaches the deposit broker's account interface (docs/specs/deposit.md,
Depositing through an API).

A person connects their own repository account on the Settings page. The browser goes to the
deposit broker directly, through the reverse proxy, never through the app: to sign in at the
repository (OAuth), or with a token they paste. The app's part is to issue a ticket for the person
signed in and to tell the page where the broker is. `DD_APP_DEPOSIT_BROKER_URL` is that place: a
path on the app's own origin, such as `/deposit-broker`, under which the reverse proxy passes
`/connect/` on to the broker and nothing else.

Without the setting, or without a deposit broker the harness can ask for drafts, the page offers
no repository account and every repository is deposited to by hand.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from dd_sdk.credentials import ConfigError

DEPOSIT_BROKER_URL_VARIABLE = "DD_APP_DEPOSIT_BROKER_URL"
_PATH = re.compile(r"(/[A-Za-z0-9._-]+)+")


def deposit_broker_path(env: Mapping[str, str]) -> str | None:
    """The deposit broker's path on the app's origin, without a trailing slash, or `None` if the
    setting is unset. Raises `ConfigError` for anything but a plain absolute path."""
    value = (env.get(DEPOSIT_BROKER_URL_VARIABLE) or "").strip().rstrip("/")
    if not value:
        return None
    if not _PATH.fullmatch(value):
        raise ConfigError(
            f"{DEPOSIT_BROKER_URL_VARIABLE} must be a path on the app's own origin, "
            "such as /deposit-broker"
        )
    return value
