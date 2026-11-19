"""Factory and console script (`dd-advisor-files`) for the File Archivist.

`DD_FILES_SUMMARISER` chooses its summary (`config/examples/agents.env`): `model`, the default, or
`template`, the rules' own. The summariser, its model settings and its fallbacks are
`dd_sdk.summary`'s; the system prompt is `system_prompt.md` beside this module. Each format and each
check is decided by rule whichever summariser runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dd_agent_advisor_files.agent import FileArchivist
from dd_sdk import summary

SWITCH = "DD_FILES_SUMMARISER"
DEFAULT: Literal["template", "model"] = "model"

build, main = summary.factory(
    FileArchivist, SWITCH, Path(__file__).with_name("system_prompt.md"), default=DEFAULT
)
