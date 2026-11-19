"""The operator's privacy notice for this instance, which the app's footer links to
(docs/specs/app.md).

The app processes personal data on its operator's behalf: a person's name and ORCID iD, their
conversations, projects and run records. The operator, not the Data Director project, decides why
and how, so the operator owes the people who sign in a privacy notice of its own. The project's
notice covers only its documentation site and its work on GitHub.

`DD_PRIVACY_NOTICE_URL` is where that notice is. `dd.py apply` and `data-director apply` write it
to `app.env` from `privacy_notice` in `deployment.yaml`. Unset, the footer shows no link: the app
does not point to a notice that does not exist, nor to the project's, which would not cover the
instance.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from dd_sdk.credentials import ConfigError

NOTICE_URL_VARIABLE = "DD_PRIVACY_NOTICE_URL"
# An absolute https URL with a host and no spaces, userinfo or script scheme. The same rule as
# `privacy_notice` in `deployment.yaml` (scripts/ddtool/deployment.py).
_URL = re.compile(r"https://[^\s/@?#]+(?:[/?#]\S*)?")


def notice_url(env: Mapping[str, str]) -> str | None:
    """The operator's privacy notice address, or `None` if the setting is unset or empty. Raises
    `ConfigError` for anything but an absolute https URL, so a wrong setting stops the app at
    start-up and never reaches a link in the page."""
    value = (env.get(NOTICE_URL_VARIABLE) or "").strip()
    if not value:
        return None
    if not _URL.fullmatch(value):
        raise ConfigError(
            f"{NOTICE_URL_VARIABLE} must be an https URL, such as "
            "https://example.ac.uk/data-director/privacy"
        )
    return value
