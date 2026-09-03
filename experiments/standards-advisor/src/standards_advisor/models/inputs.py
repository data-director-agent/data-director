"""What the CLI hands the graph."""

from __future__ import annotations

from pydantic import Field

from standards_advisor.models.common import Frozen


class DatasetInput(Frozen):
    """A dataset as the researcher has it: some files, maybe a metadata record.

    Paths are strings rather than `Path` because this object is checkpointed, and a
    `PosixPath` in a checkpoint written on one machine is a liability on another.
    """

    files: list[str] = Field(default_factory=list)
    metadata_path: str | None = None
    title: str | None = None
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    target_repository: str | None = None
    """Where the researcher intends to deposit, if known. Feeds the §5.3 repository-fit rule."""
