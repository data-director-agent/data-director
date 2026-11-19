"""What scripts/zenodo.py says when Zenodo refuses a call."""

from __future__ import annotations

import io
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import zenodo  # noqa: E402


def refuse(code: int, body: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(request: Any, timeout: float) -> Any:
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "refused",
            Message(),
            io.BytesIO(body.encode()),
        )

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize("code", [401, 403])
def test_a_refused_token_names_the_likely_causes(
    code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    refuse(code, '{"message": "Permission denied."}', monkeypatch)
    with pytest.raises(zenodo.ZenodoError) as caught:
        zenodo.Client("https://zenodo.example/api", "token").call("GET", "/deposit/depositions/1")
    message = str(caught.value)
    assert f"returned {code}" in message
    assert "Permission denied." in message
    assert "deposit:write" in message
    assert "deposit:actions" in message


def test_other_errors_do_not_blame_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    refuse(400, '{"message": "Validation error."}', monkeypatch)
    with pytest.raises(zenodo.ZenodoError) as caught:
        zenodo.Client("https://zenodo.example/api", "token").call("GET", "/deposit/depositions/1")
    assert "Validation error." in str(caught.value)
    assert "token" not in str(caught.value)
