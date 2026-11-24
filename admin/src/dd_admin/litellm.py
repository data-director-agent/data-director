"""How the admin service reaches the LLM gateway (`deploy/llm-gateway/`): its base URL and the
read-only key it presents, which the Spend page (`dd_admin.spend`) and the Gateway page
(`dd_admin.gateway`) share. The key needs only the `proxy_admin_viewer` role; it is sent to the
gateway and shown nowhere."""

from __future__ import annotations

from dataclasses import dataclass, field

from dd_admin.settings import AdminSettings
from dd_admin.system import System


@dataclass(frozen=True)
class Gateway:
    """The gateway's base URL and the headers that carry the key."""

    base: str
    headers: dict[str, str] = field(repr=False)


def connect(settings: AdminSettings, system: System) -> Gateway | str | None:
    """The gateway to ask, the reason it cannot be asked, or None when none is configured."""
    if not settings.litellm_url:
        return None
    if settings.litellm_key_file is None:
        return "no gateway key: set DD_ADMIN_LITELLM_KEY_FILE or load the litellm-key credential"
    key = (system.read_text(settings.litellm_key_file) or "").strip()
    if not key:
        return f"the gateway key at {settings.litellm_key_file} cannot be read"
    return Gateway(settings.litellm_url.rstrip("/"), {"Authorization": f"Bearer {key}"})
