"""The strict check of a chart's values: a value is supported only when the
number itself is written in a passage it cites.

A passage writes numbers in many ways, so every number found in it is read
in every way it can mean: ``1.906`` is 1.906 and 1906 (German thousands),
``1,9 Mio.`` is 1.9 and 1 900 000, ``12,5 %`` is 12.5 and 0.125. A value
matches when it equals one of the readings; there is no tolerance beyond
float precision, because a number off by one is a different number.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

NUMBER_CHECK = "number-match-v1"

# a number with optional sign and digit groups, then an optional scale or percent
_NUMBER = re.compile(
    r"(?<![\w.,])(?P<sign>[-−–]?)(?P<digits>\d+(?:[.,'’   ]\d+)*)"
    r"(?:\s*(?P<unit>%|percent\b|prozent\b|mio\b\.?|million(?:s|en)?\b|mrd\b\.?|"
    r"milliarde(?:n)?\b|billion(?:s)?\b|bn\b|tsd\b\.?|thousand(?:s)?\b|tausend\b|k\b))?",
    re.IGNORECASE,
)
_SCALES = {
    "mio": 1e6,
    "million": 1e6,
    "mrd": 1e9,
    "milliarde": 1e9,
    "billion": 1e9,
    "bn": 1e9,
    "tsd": 1e3,
    "thousand": 1e3,
    "tausend": 1e3,
    "k": 1e3,
}


def _plain(digits: str) -> set[float]:
    """The values one written digit group can mean, before scale and sign."""
    digits = re.sub(r"['’   ]", "", digits)
    dots, commas = digits.count("."), digits.count(",")
    if dots and commas:
        # the later separator is the decimal one, the other groups thousands
        decimal = "." if digits.rfind(".") > digits.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        return {float(digits.replace(thousands, "").replace(decimal, "."))}
    sep = "." if dots else "," if commas else ""
    if not sep:
        return {float(digits)}
    groups = digits.split(sep)
    readings: set[float] = set()
    if all(len(g) == 3 for g in groups[1:]):
        readings.add(float("".join(groups)))  # thousands separators
    if len(groups) == 2:
        readings.add(float(".".join(groups)))  # a decimal separator
    return readings


def readings(text: str) -> set[float]:
    """Every value the numbers written in ``text`` can mean."""
    found: set[float] = set()
    for match in _NUMBER.finditer(text):
        values = _plain(match["digits"])
        if match["sign"]:
            values = {-v for v in values}
        unit = (match["unit"] or "").lower().rstrip(".")
        scale = next((f for name, f in _SCALES.items() if unit.startswith(name)), None)
        if unit in ("%", "percent", "prozent"):
            values |= {v / 100 for v in values}
        elif scale is not None:
            values |= {v * scale for v in values}
        found |= values
    return found


def written_in(value: float, texts: Iterable[str]) -> bool:
    """Whether ``value`` is one of the readings of a number in the texts."""
    return any(
        math.isclose(value, r, rel_tol=1e-9, abs_tol=1e-12) for t in texts for r in readings(t)
    )
