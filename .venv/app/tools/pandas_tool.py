"""Sandboxed-ish execution of pandas snippets against a dataset."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.tools.reader import read_csv


def run_pandas_code(path: str | Path, code: str) -> str:
    """Execute pandas code with `df` bound to the dataset and return repr output."""
    df = read_csv(path)
    namespace: dict = {"df": df, "pd": pd}
    result = eval(code, namespace)  # noqa: S307 - intended for local analyst use
    if isinstance(result, pd.DataFrame):
        return result.to_string()
    return str(result)


AGGREGATIONS = {"sum", "mean", "count", "min", "max", "median"}


def group_by(
    path: str | Path,
    by: str | list[str],
    values: str | list[str],
    agg: str = "sum",
) -> str:
    """Group rows by ``by`` and aggregate ``values`` with ``agg``."""
    if agg not in AGGREGATIONS:
        raise ValueError(f"agg must be one of {sorted(AGGREGATIONS)}, got '{agg}'")
    df = read_csv(path)
    by = [by] if isinstance(by, str) else list(by)
    values = [values] if isinstance(values, str) else list(values)

    missing = [c for c in by + values if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in dataset: {missing}")

    out = df.groupby(by, dropna=False)[values].agg(agg).reset_index()
    return out.to_string()
