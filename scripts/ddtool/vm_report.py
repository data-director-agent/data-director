"""What every check of `dd.py doctor` on a VM shares: the report it fills, the base each group of
checks builds on, and the small helpers that name a commit or a unit's journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ddtool.vm import System, Vm, domain


@dataclass
class Report:
    """What doctor found: problems (each with its fix), notes, and checks it could not make."""

    problems: list[tuple[str, str | None]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def problem(self, text: str, fix: str | None = None) -> None:
        self.problems.append((text, fix))

    def note(self, text: str) -> None:
        self.notes.append(text)

    def skip(self, text: str) -> None:
        self.skipped.append(text)

    def print(self) -> int:
        for note in self.notes:
            print(f"note: {note}")
        if self.skipped:
            print(
                f"skipped, as this user may not read them (run with sudo to check): "
                f"{'; '.join(self.skipped)}"
            )
        for text, fix in self.problems:
            print(f"problem: {text}")
            if fix:
                print(f"    fix: {fix}")
        print("All good." if not self.problems else f"{len(self.problems)} problem(s).")
        return 1 if self.problems else 0

    def as_json(self, target: dict[str, Any]) -> dict[str, Any]:
        """The report as one JSON document, for a program to read: the admin service shows it
        (admin/, docs/guide/operations/admin.md). `target` says what was checked."""
        return {
            "target": target,
            "problems": [{"text": text, "fix": fix} for text, fix in self.problems],
            "notes": self.notes,
            "skipped": self.skipped,
        }


def short(sha: str | None) -> str:
    return (sha or "none")[:10]


def journal(unit: str) -> str:
    return f"journalctl -u {unit} -n 50 --no-pager"


@dataclass
class Checks:
    """The VM a group of checks looks at, and the report they add to."""

    system: System
    vm: Vm
    report: Report = field(default_factory=Report)

    @property
    def tool(self) -> str:
        return "sudo data-director"

    @property
    def install(self) -> str:
        return (
            f"pull the clone, then sudo {self.vm.clone}/deploy/install.sh "
            f"--domain {domain(self.system, self.vm)}"
        )
