"""Pydantic v2 models — the source of truth for every schema in `schemas/`.

The JSON Schema files are generated from these by `scripts/export_schemas.py` and a test
byte-compares them, so the committed schemas are authoritative-by-construction for anything
outside Python without anyone having to keep two definitions in step.

Only the three published document types are re-exported. Internal stage payloads
(`models.candidates`) are imported from their module, so that "is this part of the §6 contract"
is answerable by looking at an import.
"""

from standards_advisor.models.profile import DatasetProfile
from standards_advisor.models.provenance import ProvDocument
from standards_advisor.models.recommendations import RecommendationsDocument

__all__ = ["DatasetProfile", "ProvDocument", "RecommendationsDocument"]
