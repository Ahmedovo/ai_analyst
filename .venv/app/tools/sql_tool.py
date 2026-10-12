"""Query a CSV dataset using SQL against an in-memory table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

#: Replace `{table}` in a query with the in-memory table name.
TABLE_ALIAS = "data"


def query_csv(path: str | Path, sql: str) -> pd.DataFrame:
    """Load a CSV into memory and run a SQL query against it.

    Uses DuckDB when installed (reads the CSV directly), otherwise falls
    back to SQLite. In either case ``{table}`` in the query is replaced
    with the table to select from.
    """
    try:
        import duckdb  # type: ignore

        table = f"read_csv_auto('{Path(path).as_posix()}')"
        return duckdb.sql(sql.replace("{table}", table)).df()
    except ImportError:
        import warnings
        warnings.warn("DuckDB not installed. Using slow, memory-intensive SQLite fallback.")
        
        con = sqlite3.connect(":memory:")
        
        # Read and insert in chunks so the entire file is never in RAM at once
        chunksize = 100_000 
        for chunk in pd.read_csv(path, chunksize=chunksize):
            chunk.to_sql(TABLE_ALIAS, con, index=False, if_exists="append")
            
        return pd.read_sql_query(sql.replace("{table}", TABLE_ALIAS), con)
