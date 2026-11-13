"""Where the browser reaches the model broker's enrolment interface (docs/specs/model-accounts.md,
Enrolment).

A person adds their own model account on the Profile page. The browser sends the key straight to
the model broker, never to the app; the app's part is to issue an enrolment ticket for the person
signed in and to tell the page where the broker is. `DD_APP_MODEL_BROKER_URL` is that place: a
path on the app's own origin, such as `/broker`, under which the reverse proxy passes
`/enrolment/` on to the broker and nothing else. A path, not a URL, so that the browser's requests
stay on one origin and the broker needs no cross-origin rules.

Without the setting, or without the harness minting model grants, the page offers no account.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from dd_sdk.credentials import ConfigError

BROKER_URL_VARIABLE = "DD_APP_MODEL_BROKER_URL"
# One or more path segments of letters, digits, `-`, `_` and `.`, from the root.
_PATH = re.compile(r"(/[A-Za-z0-9._-]+)+")


def broker_path(env: Mapping[str, str]) -> str | None:
    """The broker's path on the app's origin, without a trailing slash, or `None` if the setting
    is unset. Raises `ConfigError` for anything but a plain absolute path."""
    value = (env.get(BROKER_URL_VARIABLE) or "").strip().rstrip("/")
    if not value:
        return None
    if not _PATH.fullmatch(value):
        raise ConfigError(
            f"{BROKER_URL_VARIABLE} must be a path on the app's own origin, such as /broker"
        )
    return value
