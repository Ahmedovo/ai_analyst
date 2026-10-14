"""Encoding-tolerant CSV loading shared by every tool.

Real-world CSVs are often *not* UTF-8: files exported from Excel on Windows
are usually **Windows-1252 (ANSI)**, where bytes such as ``0xA0``
(non-breaking space) or ``0xF6`` (o-umlaut) are valid but make a strict
UTF-8 decoder fail. A single such byte used to make *every* tool fail — so a
whole run returned no data. All tools now load CSVs through :func:`read_csv`,
which detects the encoding instead of assuming UTF-8.
"""

from __future__ import annotations

import codecs
from pathlib import Path

import pandas as pd

#: Encodings tried, in order, for files without a byte-order mark.
#: ``utf-8`` first (the common case), then ``cp1252`` for Windows/Excel
#: exports, then ``latin-1`` — which never raises, so it always terminates
#: the search and guarantees *some* successful read.
FALLBACK_ENCODINGS = ("utf-8", "cp1252", "latin-1")

#: Byte-order marks identify an encoding unambiguously. Order matters:
#: UTF-32 BOMs start with the UTF-16 BOM bytes, so they are checked first.
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def detect_encoding(path: str | Path) -> str:
    """Return the encoding to decode ``path`` with.

    A byte-order mark wins; otherwise the first of ``utf-8`` / ``cp1252``
    that decodes the whole file, falling back to ``latin-1`` (which never
    fails). UTF-16 is only chosen when a BOM is present, because a BOM-less
    UTF-16 decoder "succeeds" on almost any byte sequence and would mask the
    real encoding.
    """
    data = Path(path).read_bytes()
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return encoding
    for encoding in FALLBACK_ENCODINGS:
        try:
            data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"  # unreachable: latin-1 never raises


def read_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    """Read a CSV with automatic encoding detection.

    Tries UTF-8 (BOM-tolerant) first — one pass in the common case — and only
    re-reads with a detected legacy encoding if UTF-8 fails. kwargs are passed
    straight to :func:`pandas.read_csv`.
    """
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding=detect_encoding(path), **kwargs)
