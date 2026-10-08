"""Dataset profiling: shape, dtypes, missing values, sample rows. to know What data am I working with?"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def profile_dataframe(path: str | Path) -> dict:
    df = pd.read_csv(path)
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing": {col: int(count) for col, count in df.isna().sum().items()},
        "duplicate_rows": int(df.duplicated().sum()),
        "sample": df.head(5).to_dict(orient="records"),
    }
