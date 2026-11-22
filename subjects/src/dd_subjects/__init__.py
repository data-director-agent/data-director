"""Subject classifications a researcher's field of study can be suggested from.

Each scheme is a published classification of fields of research, held as data with its source,
version and licence: the OECD Fields of Research and Development (`oecd-fos`) and the ANZSRC
2020 Fields of Research (`anzsrc-for`). `suggestions` gives a scheme's labels in code order, each
broad field before the fields under it, for a person to choose from or ignore.
"""

from dd_subjects.schemes import SCHEMES, Scheme, Term, scheme, suggestions

__all__ = ["SCHEMES", "Scheme", "Term", "scheme", "suggestions"]
