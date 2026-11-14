"""The operator's privacy notice setting (`dd_app.privacy`)."""

from __future__ import annotations

import pytest

from dd_app.privacy import NOTICE_URL_VARIABLE, notice_url
from dd_sdk.credentials import ConfigError


@pytest.mark.parametrize("env", [{}, {NOTICE_URL_VARIABLE: ""}, {NOTICE_URL_VARIABLE: "  "}])
def test_no_notice_when_unset_or_empty(env: dict[str, str]) -> None:
    assert notice_url(env) is None


def test_an_https_url_is_used_as_written_without_surrounding_space() -> None:
    url = "https://example.ac.uk/data-director/privacy?lang=en#top"
    assert notice_url({NOTICE_URL_VARIABLE: f"  {url} "}) == url


@pytest.mark.parametrize(
    "value",
    [
        "http://example.ac.uk/privacy",  # not https
        "javascript:alert(1)",  # a script, not a page
        "//example.ac.uk/privacy",  # no scheme
        "/privacy",  # a path, which would point at the app's own origin
        "https://",  # no host
        "https://user:pass@example.ac.uk/privacy",  # credentials in a link
        "https://example.ac.uk/my privacy notice",  # a space
        "example.ac.uk/privacy",
    ],
)
def test_anything_but_an_absolute_https_url_stops_the_app(value: str) -> None:
    with pytest.raises(ConfigError, match=NOTICE_URL_VARIABLE):
        notice_url({NOTICE_URL_VARIABLE: value})
