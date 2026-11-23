"""Factory and console script (`dd-advisor-storage`) for the Storage Adviser.

`DD_STORAGE_SUMMARISER` chooses its summary (`config/examples/agents.env`): `model`, the default,
or `template`, the rules' own. The summariser, its model settings and its fallbacks are
`dd_sdk.summary`'s; the system prompt is `system_prompt.md` beside this module. Which services may
hold the data, and every concern, are decided by rule whichever summariser runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dd_agent_advisor_storage.agent import StorageAdviser
from dd_sdk import summary

SWITCH = "DD_STORAGE_SUMMARISER"
DEFAULT: Literal["template", "model"] = "model"

build, main = summary.factory(
    StorageAdviser,
    SWITCH,
    Path(__file__).with_name("system_prompt.md"),
    default=DEFAULT,
    module=__name__,
)
