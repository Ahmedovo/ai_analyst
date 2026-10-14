"""Chart creation from a declarative spec, saved under generated/charts/."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from app.tools.reader import read_csv  # noqa: E402

#: absolute so the agent and the API serve the same directory regardless of cwd
CHARTS_DIR = Path(__file__).resolve().parents[2] / "generated" / "charts"
CHART_TYPES = ("bar", "line", "histogram", "scatter")


def create_chart(
    path: str | Path,
    chart_type: str,
    x: str | None = None,
    y: str | None = None,
    title: str | None = None,
    output_name: str | None = None,
) -> str:
    """Render a chart from a spec and return the saved PNG path.

    Supported types: ``bar`` (summed per x-category), ``line``, ``histogram``
    (x only), ``scatter``.
    """
    chart_type = chart_type.lower()
    if chart_type not in CHART_TYPES:
        raise ValueError(f"chart_type must be one of {CHART_TYPES}, got '{chart_type}'")

    df = read_csv(path)
    needs_xy = chart_type in ("bar", "line", "scatter")
    if needs_xy and not (x and y):
        raise ValueError(f"chart_type '{chart_type}' requires both x and y columns")
    if chart_type == "histogram" and not x:
        raise ValueError("chart_type 'histogram' requires x (the value column)")
    for col in {c for c in (x, y) if c}:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found. Columns: {list(df.columns)}")

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))

    if chart_type == "bar":
        data = df.groupby(x, dropna=False)[y].sum() if df[x].duplicated().any() else df.set_index(x)[y]
        data.plot(kind="bar", ax=ax, color="#4C72B0")
        ax.set_xlabel(x)
        ax.set_ylabel(f"{y} (summed)")
    elif chart_type == "line":
        ax.plot(df[x], df[y], marker="o", color="#4C72B0")
        ax.set_xlabel(x)
        ax.set_ylabel(y)
    elif chart_type == "histogram":
        ax.hist(pd.to_numeric(df[x], errors="coerce").dropna(), bins=20, color="#4C72B0")
        ax.set_xlabel(x)
        ax.set_ylabel("frequency")
    elif chart_type == "scatter":
        ax.scatter(df[x], df[y], alpha=0.7, color="#4C72B0")
        ax.set_xlabel(x)
        ax.set_ylabel(y)

    if title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    safe_name = output_name or f"{chart_type}_{x or ''}_{y or ''}".strip("_")
    output = CHARTS_DIR / f"{safe_name}.png"
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return str(output)
