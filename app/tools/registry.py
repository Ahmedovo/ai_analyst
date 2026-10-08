"""Tool registry: neutral schemas + dispatcher for the analyst agent.

Each tool is a plain Python function whose first argument is the dataset
path (bound by the agent, not sent to the model). ``TOOL_DEFINITIONS``
holds provider-neutral JSON Schema declarations that any function-calling
API can consume.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.tools.profiler import profile_dataframe
from app.tools.pandas_tool import group_by as _group_by
from app.tools.sql_tool import query_csv
from app.tools.statistics import calculate_statistics, detect_anomalies
from app.tools.validation import validate_data
from app.tools.visualization import create_chart as _create_chart


# ---------------------------------------------------------------------------
# Tool implementations (dataset-bound)
# ---------------------------------------------------------------------------

def profile_dataset(dataset: str | Path) -> dict:
    """Shape, dtypes, missing values, duplicates, sample rows."""
    return profile_dataframe(dataset)


def execute_sql(dataset: str | Path, sql: str) -> str:
    """Run a SQL query; ``{table}`` is replaced with the in-memory table."""
    result = query_csv(dataset, sql)
    body = result.head(100).to_string()
    if len(result) > 100:
        body += f"\n[... {len(result)} rows total, showing first 100]"
    return f"rows returned: {len(result)}\n{body}"


def group_by(dataset: str | Path, by: list[str], values: list[str], agg: str = "sum") -> str:
    """Group and aggregate in pandas (simpler than SQL for basic splits)."""
    return _group_by(dataset, by, values, agg)


def statistics(dataset: str | Path, columns: list[str] | None = None) -> dict:
    """Descriptive statistics (+ correlations when >1 column selected)."""
    return calculate_statistics(dataset, columns)


def anomalies(
    dataset: str | Path,
    column: str,
    method: str = "iqr",
    threshold: float | None = None,
) -> dict:
    """Detect outliers in a numeric column (IQR or z-score)."""
    return detect_anomalies(dataset, column, method=method, threshold=threshold)


def chart(
    dataset: str | Path,
    chart_type: str,
    x: str | None = None,
    y: str | None = None,
    title: str | None = None,
    output_name: str | None = None,
) -> str:
    """Render a chart from a spec and return the saved PNG path."""
    return _create_chart(
        dataset, chart_type, x=x, y=y, title=title, output_name=output_name
    )


def validation(
    dataset: str | Path, rules: list[dict[str, Any]] | None = None
) -> dict:
    """Check data quality against rules; omit rules for the default suite."""
    return validate_data(dataset, rules)


#: name -> implementation (dataset is bound by the dispatcher)
TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "profile_dataset": profile_dataset,
    "execute_sql": execute_sql,
    "group_by": group_by,
    "calculate_statistics": statistics,
    "detect_anomalies": anomalies,
    "create_chart": chart,
    "validate_data": validation,
}


# ---------------------------------------------------------------------------
# Provider-neutral tool schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "profile_dataset",
        "description": (
            "Profile the dataset: row/column counts, dtypes, missing values, "
            "duplicate rows and the first sample rows. Call this first to "
            "understand the data."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "execute_sql",
        "description": (
            "Run a SQL query against the dataset. Use the placeholder {table} "
            "wherever the table name belongs, e.g. "
            "SELECT region, SUM(revenue) FROM {table} GROUP BY region"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SQL SELECT statement using {table} as the source.",
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "group_by",
        "description": (
            "Group rows by one or more columns and aggregate numeric columns. "
            "Simpler than SQL for basic splits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "by": {"type": "array", "items": {"type": "string"},
                       "description": "Columns to group by"},
                "values": {"type": "array", "items": {"type": "string"},
                           "description": "Numeric columns to aggregate"},
                "agg": {"type": "string", "enum": ["sum", "mean", "count", "min", "max", "median"],
                        "description": "Aggregation function (default: sum)"},
            },
            "required": ["by", "values"],
        },
    },
    {
        "name": "calculate_statistics",
        "description": (
            "Descriptive statistics (count, mean, std, min, quartiles, max) for "
            "numeric columns, plus pairwise correlations when several columns "
            "are selected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"},
                            "description": "Numeric columns to summarise; omit for all."},
            },
            "required": [],
        },
    },
    {
        "name": "detect_anomalies",
        "description": (
            "Detect outliers in a numeric column (IQR or z-score method) and "
            "return the bounds plus the offending rows."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "column": {"type": "string", "description": "Numeric column to test"},
                "method": {"type": "string", "enum": ["iqr", "zscore"],
                           "description": "Detection method (default: iqr)"},
                "threshold": {"type": "number",
                              "description": "IQR multiplier (default 1.5) or z-score cutoff (default 3)"},
            },
            "required": ["column"],
        },
    },
    {
        "name": "create_chart",
        "description": (
            "Render a chart and save it as PNG under generated/charts/. "
            "Returns the file path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string",
                               "enum": ["bar", "line", "histogram", "scatter"]},
                "x": {"type": "string",
                      "description": "Column for the x-axis (histogram: the value column)"},
                "y": {"type": "string",
                      "description": "Column for the y-axis (unused for histogram)"},
                "title": {"type": "string", "description": "Chart title"},
                "output_name": {"type": "string", "description": "File name without extension"},
            },
            "required": ["chart_type"],
        },
    },
    {
        "name": "validate_data",
        "description": (
            "Validate data quality against rules (nulls, ranges, allowed values, "
            "uniqueness, numeric type, row-level expression consistency). Returns "
            "pass/fail per rule with sample offending rows. Omit 'rules' to run "
            "the default suite (nulls in every column + duplicate rows)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rules": {
                    "type": "array",
                    "description": "Rules to evaluate; omit for the default quality checks.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "check": {"type": "string",
                                      "enum": ["not_null", "unique", "numeric", "range",
                                               "allowed", "expression", "no_duplicates"]},
                            "column": {"type": "string"},
                            "min": {"type": "number", "description": "For range: inclusive lower bound"},
                            "max": {"type": "number", "description": "For range: inclusive upper bound"},
                            "values": {"type": "array", "items": {"type": "string"},
                                       "description": "For allowed: permitted values"},
                            "expr": {"type": "string",
                                     "description": "For expression: pandas query condition that must hold "
                                                    "for every row, e.g. units * unit_price <= revenue + 0.01"},
                            "description": {"type": "string", "description": "Why this rule matters"},
                        },
                        "required": ["check"],
                    },
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    """Serialise numpy/pandas scalars produced by tool results."""
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


def run_tool(name: str, arguments: dict[str, Any] | None, dataset: str | Path) -> str:
    """Execute a tool call and return a string payload for the model.

    Raises ``ValueError`` for unknown tools; implementations may raise on
    bad arguments (the agent converts exceptions into model-readable errors).
    """
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        raise ValueError(
            f"Unknown tool '{name}'. Available tools: {', '.join(TOOL_FUNCTIONS)}"
        )
    result = fn(dataset, **(arguments or {}))
    if isinstance(result, str):
        return result
    return json.dumps(result, default=_json_default, ensure_ascii=False, indent=2)
