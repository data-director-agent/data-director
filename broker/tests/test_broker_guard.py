"""The broker sends a key only to an allow-listed https origin, and not to a private or reserved
address unless the operator said so (docs/specs/model-accounts.md, Security)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from dd_broker.guard import BaseUrlRefused, check_base_url, origin

ALLOWED = ["https://models.example.ac.uk"]


def resolving_to(*addresses: str) -> Callable[[str, int], list[str]]:
    def resolve(host: str, port: int) -> list[str]:
        return list(addresses)

    return resolve


def test_an_allow_listed_public_origin_is_pinned_to_the_address_checked() -> None:
    target = check_base_url(
        "https://models.example.ac.uk/v1", ALLOWED, resolve=resolving_to("93.184.215.14")
    )
    assert target.url == "https://93.184.215.14/v1"
    assert target.headers == {"host": "models.example.ac.uk"}
    assert target.extensions == {"sni_hostname": "models.example.ac.uk"}


@pytest.mark.parametrize(
    "url",
    [
        "http://models.example.ac.uk",
        "https://user:pass@models.example.ac.uk",
        "https://models.example.ac.uk/?x=1",
        "https://other.example.ac.uk",
        "https://models.example.ac.uk:8443",
        "ftp://models.example.ac.uk",
    ],
)
def test_a_url_that_is_not_a_plain_allow_listed_https_origin_is_refused(url: str) -> None:
    with pytest.raises(BaseUrlRefused):
        check_base_url(url, ALLOWED, resolve=resolving_to("93.184.215.14"))


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "100.64.0.1",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:10.0.0.5",
        "224.0.0.1",
    ],
)
def test_an_allow_listed_name_resolving_to_a_private_address_is_refused(address: str) -> None:
    with pytest.raises(BaseUrlRefused):
        check_base_url(
            "https://models.example.ac.uk", ALLOWED, resolve=resolving_to("93.184.215.14", address)
        )


def test_a_private_address_is_allowed_only_where_the_operator_said_so() -> None:
    target = check_base_url(
        "https://models.example.ac.uk",
        (),
        private=ALLOWED,
        resolve=resolving_to("10.0.0.5"),
    )
    assert target.url == "https://10.0.0.5"


def test_a_name_that_does_not_resolve_is_refused() -> None:
    def fails(host: str, port: int) -> list[str]:
        raise OSError("no such host")

    with pytest.raises(BaseUrlRefused):
        check_base_url("https://models.example.ac.uk", ALLOWED, resolve=fails)


def test_origins_are_compared_without_case_or_the_default_port() -> None:
    assert origin("https://Models.Example.ac.uk:443/v1") == "https://models.example.ac.uk"
    assert origin("https://models.example.ac.uk:8443") == "https://models.example.ac.uk:8443"
