"""What the CLI hands the graph."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from standards_advisor.models.common import Frozen, LifecyclePhase


class DatasetInput(Frozen):
    """A dataset as the researcher has it — or, before Phase 1, as they plan it.

    Paths are strings rather than `Path` because this object is checkpointed, and a
    `PosixPath` in a checkpoint written on one machine is a liability on another.

    One model rather than a discriminated union on `phase`. A union would let the type checker
    prove that a pre-collection input has no `files`, but it would cost narrowing at every read
    site and split `RunManifest.inputs` in two, for one invariant. `_check_phase_inputs` buys
    that invariant directly, in one place, and every field added for §8 is optional — so an
    `input.json` or a checkpoint written before §8 still loads.
    """

    phase: LifecyclePhase = LifecyclePhase.COLLECTED
    """Which Blueprint entry point this run serves (§8). Defaults to the pre-§8 behaviour."""

    files: list[str] = Field(default_factory=list)
    metadata_path: str | None = None
    title: str | None = None
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    target_repository: str | None = None
    """Where the researcher intends to deposit, if known. Feeds the §5.3 repository-fit rule."""

    readme_path: str | None = None
    """A README describing the project. R5's output, and the source of title and abstract when
    no metadata record exists. Permitted in either phase — a collected dataset has one too."""

    dictionary_path: str | None = None
    """A draft data dictionary as Frictionless Table Schema (§8). Required pre-collection: it is
    what stands in for the columns tier 1 would otherwise infer from file contents."""

    answers_path: str | None = None
    """Answers to the intake questions, supplied up front instead of interactively.

    Its presence is what makes a pre-collection run non-interactive: `elicit` reads these and
    does not pause. That is how the test suite drives the whole pipeline in one `invoke()`, and
    how the CLI stays usable when stdin is not a terminal."""

    formats_planned: list[str] = Field(default_factory=list)
    """Formats the researcher intends to write, if stated before being asked. Kept apart from
    the profile's `formats_found` throughout — planning to write XLSX and having written it are
    different facts, and R3.3 answers them differently."""

    @model_validator(mode="after")
    def _check_phase_inputs(self) -> Self:
        """Reject the two pre-collection combinations that cannot mean anything.

        Not defensive coding: without the second check, a pre-collection run handed data files
        would profile them and still report itself as Phase 1, and the output would claim to be
        advice about a dataset that does not exist yet.

        This raises where the rest of the codebase records — see `errors`. The distinction holds:
        an inconsistent `DatasetInput` is a caller's mistake, caught before the graph starts, not
        something the pipeline learned about the dataset. Nothing is said here about a *collected*
        run with no files, because that is a content outcome and `profile_node` already reports
        it as `input_missing` and an `empty` stage.
        """
        if self.phase is not LifecyclePhase.PRE_COLLECTION:
            return self
        if self.dictionary_path is None:
            raise ValueError(
                "a pre_collection run needs dictionary_path: with no data files, the draft "
                "data dictionary is the only description of the dataset's variables (§8)"
            )
        if self.files:
            raise ValueError(
                f"a pre_collection run must have no files, got {len(self.files)}; "
                "data that already exists is a collected run"
            )
        return self
