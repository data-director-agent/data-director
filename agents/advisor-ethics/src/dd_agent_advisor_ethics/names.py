"""The names the adviser checks, and what the project's inventory adds to them (#1540).

A caller gives field names (`fields`). In a project, the conductor also gives the project's
inventory (`project_file_inventory`, mixed in by `GivenProjectInventory`, docs/specs/projects.md,
invariant 6), and the adviser then checks every table's field names and every file and folder
name it lists too. Each name is checked once, and records where in the inventory it appears, so a
person can find it.

The inventory command's personal data detector has looked at what the adviser cannot: sampled
values and small text files, on the researcher's computer (docs/specs/personal-data.md). Its
findings are carried over as they are. An inventory whose findings are absent was made with no
detector; one whose findings are empty was checked and nothing was found, which does not mean
there is nothing (personal-data spec, invariant 10). The two are kept apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from dd_agent_advisor_ethics.classes import SensitivityContext
from dd_sdk.contract.inventory import FileInventory, PersonalDataFinding
from dd_sdk.inventory_hints import RULES, HintKind, Rule, hints


@dataclass(frozen=True)
class Names:
    """The distinct names to check, in order: the caller's first, then the inventory's; and for a
    name the inventory gives, the files it appears in."""

    names: tuple[str, ...] = ()
    where: dict[str, tuple[str, ...]] = field(default_factory=dict)
    from_inventory: int = 0


def names_of(context: SensitivityContext) -> Names:
    """The caller's field names, then each table's field names, file names and folder names from
    the inventory, each once."""
    order: dict[str, list[str]] = {name: [] for name in context.fields}
    inventory = context.project_file_inventory
    if inventory is not None:
        for file in inventory.inventory_files:
            path = PurePosixPath(file.file_path)
            listed = [f.name for f in file.file_fields] + [path.name, *path.parent.parts]
            for name in listed:
                paths = order.setdefault(name, [])
                if file.file_path not in paths:
                    paths.append(file.file_path)
    given = set(context.fields)
    return Names(
        names=tuple(order),
        where={name: tuple(paths) for name, paths in order.items() if paths},
        from_inventory=sum(1 for name in order if name not in given),
    )


def findings(inventory: FileInventory | None) -> list[PersonalDataFinding] | None:
    """What the inventory's detector found, from the inventory and each of its parts; None when no
    detector ran on any of it."""
    if inventory is None:
        return None
    lists = [inventory.inventory_personal_data] + [
        part.part_personal_data for part in inventory.inventory_parts or []
    ]
    ran = [found for found in lists if found is not None]
    return [finding for found in ran for finding in found] if ran else None


FREE_TEXT: tuple[Rule, ...] = tuple(rule for rule in RULES if rule.kind is HintKind.FREE_TEXT)


def free_text(inventory: FileInventory | None) -> list[str]:
    """The inventory's files whose names suggest free text, such as notes or transcripts
    (`dd_sdk.inventory_hints`): the adviser reads no content, so a person must."""
    if inventory is None:
        return []
    return [hint.path for hint in hints(inventory.inventory_files, FREE_TEXT)]
