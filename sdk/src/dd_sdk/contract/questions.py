"""The questions a drafter asks about the gaps in its draft, and a person's answers to them
(`DocumentQuestion`, `DraftAnswer`), with `Derivation`, how a value came about
(docs/specs/drafting.md). `models` re-exports each name, so that it stays within its size limit;
the field names and enum values are the LinkML schema's.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from dd_sdk.contract.base import Frozen

# A drafter's question about a gap, derived from the gap (docs/specs/drafting.md).
QUESTION_ID_PATTERN = r"^q-[0-9a-f]{16}$"


class Derivation(StrEnum):
    TEMPLATE = "template"
    MODEL = "model"
    LEXICAL = "lexical"
    REGISTRY = "registry"


class DocumentQuestion(Frozen):
    """A drafter's question about one gap in its draft: a README section, a data dictionary cell
    named by file, field and column, or a metadata record value (docs/specs/drafting.md)."""

    question_id: str = Field(pattern=QUESTION_ID_PATTERN)
    question_prompt: str
    gap_section: str | None = None
    # The part of the section, when the drafter asks a section part by part.
    gap_part: str | None = None
    gap_file: str | None = None
    gap_field: str | None = None
    gap_column: str | None = None
    # Every file whose cell the answer fills, gap_file among them, when one question asks about a
    # column several files share by name, type and format. None when it fills one cell.
    gap_files: list[str] | None = None
    # A metadata record value, by its path in the record's JSON form, such as titles[0].title.
    gap_property: str | None = None
    # Offered with the question, never placed in the document (docs/specs/drafting.md).
    suggested_answer: str | None = None
    suggestion_derivation: Derivation | None = None

    @model_validator(mode="after")
    def _one_target(self) -> DocumentQuestion:
        if (self.suggested_answer is None) != (self.suggestion_derivation is None):
            raise ValueError("a suggested answer says how it was derived, and only then")
        cell = (self.gap_file, self.gap_field, self.gap_column)
        if self.gap_part is not None and self.gap_section is None:
            raise ValueError("a question targets a part only within a README section")
        if None in cell and any(c is not None for c in cell):
            raise ValueError("a question targets a cell by file, field and column together")
        if sum(t is not None for t in (self.gap_section, self.gap_file, self.gap_property)) != 1:
            raise ValueError("a question targets one of a README section, a cell or a property")
        if self.gap_files is not None and (
            self.gap_file not in self.gap_files or len(set(self.gap_files)) != len(self.gap_files)
        ):
            raise ValueError("a question's files are distinct and include the cell's file")
        return self


class DraftAnswer(Frozen):
    """A person's answer to one of the current version's questions, placed as given."""

    answered_question: str = Field(pattern=QUESTION_ID_PATTERN)
    answer_text: str
