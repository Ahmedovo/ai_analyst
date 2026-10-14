"""Encoding robustness: CSVs that are not UTF-8 must still load in every tool.

Regression guard for the Windows-1252 (Excel/ANSI) files whose bytes such as
``0xA0`` (non-breaking space) previously made a whole run return no data.
"""

from pathlib import Path

from app.tools.profiler import profile_dataframe
from app.tools.reader import detect_encoding, read_csv
from app.tools.sql_tool import query_csv

#: "Café\u00a0phone" (NBSP) + "Ökologie" — invalid as UTF-8, valid as cp1252.
CP1252_CSV = "name,amount\nCaf\u00e9\u00a0phone,10\n\u00d6kologie,20\n".encode("cp1252")


def _write(tmp_path: Path, name: str, raw: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def test_detect_encoding_windows_1252(tmp_path):
    assert detect_encoding(_write(tmp_path, "win.csv", CP1252_CSV)) == "cp1252"


def test_detect_encoding_utf8_with_bom(tmp_path):
    raw = b"\xef\xbb\xbfa,b\n1,2\n"
    assert detect_encoding(_write(tmp_path, "bom.csv", raw)) == "utf-8-sig"


def test_detect_encoding_utf16_with_bom(tmp_path):
    raw = "a,b\n1,2\n".encode("utf-16")
    assert detect_encoding(_write(tmp_path, "u16.csv", raw)) == "utf-16"


def test_detect_encoding_latin1_fallback(tmp_path):
    # 0x81 is undefined in cp1252 but valid in latin-1
    assert detect_encoding(_write(tmp_path, "l1.csv", b"a,b\n\x81,2\n")) == "latin-1"


def test_read_csv_decodes_windows_1252(tmp_path):
    df = read_csv(_write(tmp_path, "win.csv", CP1252_CSV))
    assert df.shape == (2, 2)
    assert df["name"].iloc[0] == "Caf\u00e9\u00a0phone"
    assert int(df["amount"].sum()) == 30


def test_read_csv_plain_utf8(tmp_path):
    raw = "name,amount\ncaf\u00e9,5\n".encode("utf-8")
    assert read_csv(_write(tmp_path, "u8.csv", raw))["name"].iloc[0] == "caf\u00e9"


def test_read_csv_utf8_with_bom(tmp_path):
    raw = "name\ncaf\u00e9\n".encode("utf-8-sig")
    assert read_csv(_write(tmp_path, "bom.csv", raw))["name"].iloc[0] == "caf\u00e9"


def test_profiler_handles_windows_1252(tmp_path):
    profile = profile_dataframe(_write(tmp_path, "win.csv", CP1252_CSV))
    assert profile["rows"] == 2
    assert profile["columns"] == 2


def test_sql_handles_windows_1252(tmp_path):
    out = query_csv(
        _write(tmp_path, "win.csv", CP1252_CSV),
        "SELECT SUM(amount) AS total FROM {table}",
    )
    assert int(out["total"].iloc[0]) == 30
