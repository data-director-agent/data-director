"""The vocabularies the project chose for the dataset's subjects, as people decided them
(`standard` project facts, docs/specs/projects.md, #1391).

The librarian does not take terms from a vocabulary (TODO(#703)); it names the ones chosen in the
question about the record's subjects, so the researcher answers from them. Only a vocabulary,
ontology or terminology chosen for the whole dataset is named: a format, or a standard chosen for
one field's values, is not a source of subjects.
"""

from __future__ import annotations

from collections.abc import Sequence

from dd_sdk.contract.facts import DATASET_TARGET, FactKind, ProjectFact, StandardKind

SUBJECTS = "subjects"
TERM_SOURCES = frozenset(
    {StandardKind.CONTROLLED_VOCABULARY, StandardKind.ONTOLOGY, StandardKind.TERMINOLOGY}
)


def vocabularies(decisions: Sequence[ProjectFact]) -> list[str]:
    """The names of the vocabularies chosen for the dataset, in the order decided, once each."""
    names = (
        fact.standard_name
        for fact in decisions
        if fact.fact_kind == FactKind.STANDARD
        and fact.standard_kind in TERM_SOURCES
        and (fact.standard_target or DATASET_TARGET) == DATASET_TARGET
    )
    return list(dict.fromkeys(name for name in names if name))


def subjects_prompt(prompt: str | None, decisions: Sequence[ProjectFact]) -> str | None:
    """The subjects question, naming the vocabularies chosen; as it was when none was chosen."""
    chosen = vocabularies(decisions)
    if not chosen:
        return prompt
    said = prompt or "What is the dataset about? Give a keyword or subject."
    return f"{said} The project chose {', '.join(chosen)}: give a term from it where one fits."
