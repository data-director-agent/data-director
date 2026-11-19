"""`dd.py backup` and `dd.py restore BACKUP`: back up a VM's settings, secrets and stores, and put
them back on a clean VM (deploy/README.md, "Backups").

They are deploy/backup.sh and deploy/restore.sh, run from the clone as root, as `secret` runs
deploy/secret.sh. The nightly timer runs the copy of backup.sh that install.sh installs. In
development the stores are the developer's own, and there is nothing to back up.
"""

from __future__ import annotations

import os
from typing import NoReturn

from ddtool.common import DevError
from ddtool.vm import Vm


def run_script(target: str, command: str, args: list[str], vm: Vm | None = None) -> NoReturn:
    if target != "vm":
        raise DevError(
            f"`{command}` is for a VM deployed with deploy/install.sh (deploy/README.md, "
            '"Backups"); in development there is nothing to back up'
        )
    script = (vm or Vm()).clone / "deploy" / f"{command}.sh"
    os.execvp("bash", ["bash", str(script), *args])
