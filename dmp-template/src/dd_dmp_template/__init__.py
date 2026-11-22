"""The core requirements for a Data Management Plan, and which of them a plan's headings cover."""

from dd_dmp_template.coverage import Coverage, Passage, coverage, heading_of, names, split
from dd_dmp_template.sections import SECTIONS, Section

__all__ = ["SECTIONS", "Coverage", "Passage", "Section", "coverage", "heading_of", "names", "split"]
