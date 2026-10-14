"""Query a CSV dataset using SQL against an in-memory table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from app.tools.reader import read_csv

#: Replace `{table}` in a query with the in-memory table name.
TABLE_ALIAS = "data"


def query_csv(path: str | Path, sql: str) -> pd.DataFrame:
    """Load a CSV into memory and run a SQL query against it.

    The CSV is always read through :func:`app.tools.reader.read_csv`, so
    non-UTF-8 files (e.g. Windows-1252 Excel exports) work here exactly like
    they do in every other tool — ``read_csv_auto`` alone rejects them. DuckDB
    runs the query when installed, otherwise a SQLite fallback is used. In
    either case ``{table}`` in the query is replaced with the table to select
    from.
    """
    df = read_csv(path)
    query = sql.replace("{table}", TABLE_ALIAS)

    try:
        import duckdb  # type: ignore
    except ImportError:
        import warnings

        warnings.warn("DuckDB not installed. Using slower SQLite fallback.")
        con = sqlite3.connect(":memory:")
        try:
            df.to_sql(TABLE_ALIAS, con, index=False, if_exists="replace")
            return pd.read_sql_query(query, con)
        finally:
            con.close()

    con = duckdb.connect()
    try:
        con.register(TABLE_ALIAS, df)
        return con.execute(query).df()
    finally:
        con.close()
