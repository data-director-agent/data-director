"""Factory and console script (`dd-advisor-quality`) for the Metadata Reviewer.

`DD_QUALITY_SUMMARISER` chooses its summary (`config/examples/agents.env`): `model`, the default, or
`template`, the rules' own. The summariser, its model settings and its fallbacks are
`dd_sdk.summary`'s; the system prompt is `system_prompt.md` beside this module. The score and each
finding are decided by rule whichever summariser runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dd_agent_advisor_quality.agent import QualityReviewer
from dd_sdk import summary

SWITCH = "DD_QUALITY_SUMMARISER"
DEFAULT: Literal["template", "model"] = "model"

build, main = summary.factory(
    QualityReviewer, SWITCH, Path(__file__).with_name("system_prompt.md"), default=DEFAULT
)
