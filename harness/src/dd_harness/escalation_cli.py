"""`dd-harness escalations sweep`: send each escalation nobody has taken in time to its team again
(`dd_harness.escalation_api.sweep`, docs/specs/stewardship.md, invariant 13).

Run on a timer (`deploy/systemd/data-director-escalations.timer`). It reads the projects under
`DD_PROJECTS_DIR`, the profile `DD_PROFILE` names, whose `stewardship.reroute_after` says how long
an escalation may wait, and the mail settings of `dd_harness.mail`. It records each escalation it
sends again in the project's log, for the deployment, emails the team where the profile names an
address for it, and prints each one as a JSON line. Running it twice in a row sends nothing more.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dd_harness.escalation_api import sweep
from dd_harness.mail import notifier_for
from dd_harness.policy import load_profile
from dd_harness.settings import SettingsError, project_storage, projects_dir
from dd_sdk.contract.models import now
from dd_sdk.credentials import ConfigError


def cmd_sweep(args: argparse.Namespace) -> int:
    location = os.environ.get("DD_PROFILE")
    if not location:
        raise SettingsError("DD_PROFILE names the institutional profile the sweep applies")
    profile = load_profile(Path(location))
    try:
        notifier = notifier_for(profile, os.environ, background=False)
    except ConfigError as exc:
        raise SettingsError(str(exc)) from None
    for found in sweep(project_storage(projects_dir()), profile, notifier, now=now()):
        line = {key: found[key] for key in ("project_id", "escalation_id", "team_id")}
        sys.stdout.write(json.dumps(line) + "\n")
    return 0


def add_commands(sub: Any) -> None:
    p = sub.add_parser(
        "escalations",
        help="look after escalations to a data steward (docs/specs/stewardship.md)",
    )
    escalations = p.add_subparsers(dest="escalations_command", required=True)
    p = escalations.add_parser(
        "sweep",
        help="send each escalation nobody took within reroute_after to its team again",
    )
    p.set_defaults(func=cmd_sweep)
