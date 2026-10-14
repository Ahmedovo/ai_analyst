"""Statistical summaries and anomaly detection."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.tools.reader import read_csv


def describe_statistics(path: str | Path) -> dict:
    df = read_csv(path)
    numeric = df.select_dtypes(include="number")
    return {
        "describe": numeric.describe().to_dict(),
        "correlation": numeric.corr().to_dict() if numeric.shape[1] > 1 else {},
    }


def calculate_statistics(
    path: str | Path, columns: list[str] | None = None
) -> dict:
    """Descriptive statistics for selected (or all) numeric columns."""
    df = read_csv(path)
    numeric = df.select_dtypes(include="number")
    if columns:
        missing = [c for c in columns if c not in numeric.columns]
        if missing:
            raise ValueError(
                f"Columns not found or not numeric: {missing}. "
                f"Numeric columns: {list(numeric.columns)}"
            )
        numeric = numeric[columns]
    return {
        "describe": numeric.describe().to_dict(),
        "correlation": numeric.corr().to_dict() if numeric.shape[1] > 1 else {},
    }


def correlation_between(path: str | Path, col_a: str, col_b: str) -> float:
    df = read_csv(path)
    return float(df[col_a].corr(df[col_b]))


def detect_anomalies(
    path: str | Path,
    column: str,
    method: str = "iqr",
    threshold: float | None = None,
    max_rows: int = 50,
) -> dict:
    """Detect outliers in a numeric column using IQR or z-score.

    Returns the method, effective bounds, anomaly count, and the offending
    rows (capped at ``max_rows``).
    """
    df = read_csv(path)
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found. Columns: {list(df.columns)}")
    series = pd.to_numeric(df[column], errors="coerce")
    if series.notna().sum() == 0:
        raise ValueError(f"Column '{column}' has no numeric values")

    method = method.lower()
    if method == "iqr":
        k = 1.5 if threshold is None else float(threshold)
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        low, high = q1 - k * iqr, q3 + k * iqr
        mask = (series < low) | (series > high)
    elif method == "zscore":
        z_cutoff = 3.0 if threshold is None else float(threshold)
        std = series.std(ddof=0)
        if not std:
            raise ValueError("Standard deviation is zero; z-score method unusable")
        z = (series - series.mean()) / std
        low, high = float(series.mean() - z_cutoff * std), float(series.mean() + z_cutoff * std)
        mask = z.abs() > z_cutoff
    else:
        raise ValueError(f"method must be 'iqr' or 'zscore', got '{method}'")

    flagged = df.loc[mask.fillna(False)]
    return {
        "column": column,
        "method": method,
        "bounds": {"low": float(low), "high": float(high)},
        "n_anomalies": int(mask.sum()),
        "anomaly_rate": float(mask.mean()),
        "anomalies": flagged.head(max_rows).to_dict(orient="records"),
    }
