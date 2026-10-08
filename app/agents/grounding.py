"""Grounding check: every number in a final answer must come from a tool result.

Deterministic (no LLM): extracts numeric tokens from the answer and verifies
each one is grounded in the concatenated tool results of the run (or was part
of the user's original question).

A token is grounded when a tool-result number either matches it directly
(full / 2- / 4-decimal precision) or **rounds to exactly what the answer
displays at its stated precision** (e.g. corpus 0.2748 -> answer "0.275").
Unicode punctuation models like to emit is folded first: narrow no-break
spaces as thousands separators ("1 183.72") and the U+2212 minus sign.
"""

from __future__ import annotations

import re
from typing import Any

#: standalone numeric tokens; the (?<!\w)/(?!\w) guards skip fragments
#: glued to words such as "Q3", "v2", "10x"
_NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?(?![\w])")

#: U+2212 MINUS SIGN — models emit it instead of ASCII hyphen
_MINUS_VARIANTS = {"\u2212": "-"}

#: spaces that appear as thousands separators between digits
#: (space, nbsp, narrow nbsp, thin space, ...), never as word separators
_THOUSANDS_SPACES = "\u00a0\u202f\u2009\u2007\u3000"


def _normalize(text: str) -> str:
    """Fold Unicode punctuation into ASCII so number tokens stay intact."""
    for char, ascii_hyphen in _MINUS_VARIANTS.items():
        text = text.replace(char, ascii_hyphen)
    text = re.sub(
        rf"(?<=\d)[{re.escape(_THOUSANDS_SPACES)}](?=\d)", ",", text
    )
    return text


def extract_numbers(text: str | None) -> list[str]:
    """Return the numeric tokens found in ``text`` (order preserved)."""
    return _NUMBER_RE.findall(_normalize(text or ""))


def _as_float(token: str) -> float | None:
    try:
        return float(token.rstrip("%").replace(",", ""))
    except ValueError:
        return None


def _decimals(token: str) -> int:
    """How many decimal places the token displays (its rounding precision)."""
    core = token.rstrip("%").replace(",", "")
    return len(core.partition(".")[2]) if "." in core else 0


def _values(text: str | None) -> list[float]:
    """Numeric values of ``text`` (order preserved)."""
    values: list[float] = []
    for token in extract_numbers(text):
        value = _as_float(token)
        if value is not None:
            values.append(value)
    return values


def _collect(text: str | None) -> tuple[set[float], set[float]]:
    """Numeric tokens of ``text`` rounded to 4 and 2 decimals."""
    r4: set[float] = set()
    r2: set[float] = set()
    for value in _values(text):
        r4.add(round(value, 4))
        r2.add(round(value, 2))
    return r4, r2


def _is_grounded(
    token: str,
    value: float,
    corpus_r4: set[float],
    corpus_r2: set[float],
    corpus_values: list[float],
) -> bool:
    """True when some tool-result number justifies this answer token."""
    if round(value, 4) in corpus_r4 or round(value, 2) in corpus_r2:
        return True
    # display rounding: tolerate half of the token's last shown digit,
    # e.g. "1184" for 1183.7225 (d=0 -> tol 0.5), "0.275" for 0.2748
    tolerance = 0.5 * 10 ** (-_decimals(token)) + 1e-9
    percent = token.endswith("%")
    for candidate in corpus_values:
        if abs(value - candidate) <= tolerance:
            return True
        if percent and abs(value - candidate * 100) <= tolerance:
            return True  # "5%" is grounded by a rate of 0.05
    return False


def validate_answer(
    answer: str,
    steps: list[dict[str, Any]],
    question: str = "",
) -> dict[str, Any]:
    """Check that every number in ``answer`` is grounded in a tool result.

    Returns a verdict dict::

        {"passed": bool, "checked": int, "unsupported": [...], "tool_results": int}

    Numbers that were part of the user's own question (e.g. a year they
    mentioned) are accepted without grounding.
    """
    if not steps:
        return {
            "passed": True,
            "checked": 0,
            "unsupported": [],
            "tool_results": 0,
            "note": "no tool results to check against",
        }

    corpus_r4: set[float] = set()
    corpus_r2: set[float] = set()
    corpus_values: list[float] = []
    for step in steps:
        result = step.get("result", "")
        r4, r2 = _collect(result)
        corpus_r4 |= r4
        corpus_r2 |= r2
        corpus_values.extend(_values(result))

    question_r4, question_r2 = _collect(question)

    checked = 0
    unsupported: list[str] = []
    for token in extract_numbers(answer):
        value = _as_float(token)
        if value is None:
            continue
        if round(value, 4) in question_r4 or round(value, 2) in question_r2:
            continue  # user-supplied context, not a claim about the data
        checked += 1
        if not _is_grounded(token, value, corpus_r4, corpus_r2, corpus_values):
            unsupported.append(token)

    return {
        "passed": not unsupported,
        "checked": checked,
        "unsupported": unsupported,
        "tool_results": len(steps),
    }
