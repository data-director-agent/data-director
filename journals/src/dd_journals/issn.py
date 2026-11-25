"""ISSNs as ISO 3297 writes them: `NNNN-NNNC`, where C is a check digit, 0 to 9 or X."""

from __future__ import annotations

import re

ISSN_SHAPE = re.compile(r"^\d{4}-?\d{3}[\dX]$")


def normal_issn(value: str) -> str | None:
    """`value` as `NNNN-NNNC`, or None if it is not shaped like an ISSN. The check digit is not
    checked: `valid_issn` does that."""
    text = value.strip().upper()
    if not ISSN_SHAPE.match(text):
        return None
    digits = text.replace("-", "")
    return f"{digits[:4]}-{digits[4:]}"


def check_digit(first_seven: str) -> str:
    """The ISSN check digit of seven digits: weights 8 down to 2, modulus 11, 10 written X."""
    total = sum(int(d) * w for d, w in zip(first_seven, range(8, 1, -1), strict=True))
    digit = (11 - total % 11) % 11
    return "X" if digit == 10 else str(digit)


def valid_issn(value: str) -> str | None:
    """`value` as `NNNN-NNNC` if it is an ISSN whose check digit is right, otherwise None."""
    issn = normal_issn(value)
    if issn is None:
        return None
    digits = issn.replace("-", "")
    return issn if check_digit(digits[:7]) == digits[7] else None
