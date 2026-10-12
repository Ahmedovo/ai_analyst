"""Data-quality validation rules for the ``validate_data`` tool.

A rule is a plain dict:

    {"check": "not_null", "column": "revenue"}
    {"check": "range", "column": "units", "min": 0}
    {"check": "allowed", "column": "region", "values": ["North", "South"]}
    {"check": "unique", "column": "order_id"}
    {"check": "numeric", "column": "revenue"}
    {"check": "expression", "expr": "units * unit_price <= revenue + 0.01"}
    {"check": "no_duplicates"}

Omitting rules runs the default suite (nulls in every column + duplicate rows).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

SAMPLE_LIMIT = 5

VALID_CHECKS = (
    "not_null",
    "unique",
    "numeric",
    "range",
    "allowed",
    "expression",
    "no_duplicates",
)


def _evaluate(df: pd.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise ValueError(f"Each rule must be an object, got: {rule!r}")
    check = rule.get("check", "not_null")
    if check not in VALID_CHECKS:
        raise ValueError(f"Unknown check '{check}'. Valid checks: {VALID_CHECKS}")
    column = rule.get("column")

    if check == "no_duplicates":
        mask = df.duplicated()
        label: dict[str, Any] = {"check": check, "column": None}
    elif check == "expression":
        # condition that must hold for every row (column-independent)
        expr = rule.get("expr")
        if not expr:
            raise ValueError("check 'expression' requires 'expr'")
        try:
            matched = df.query(expr)
        except Exception as exc:  # noqa: BLE001 - surface parse errors to the model
            raise ValueError(f"Invalid expression {expr!r}: {exc}") from exc
        mask = ~df.index.isin(matched.index)
        label = {"check": check, "column": None}
    else:
        if not column:
            raise ValueError(f"check '{check}' requires a 'column'")
        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found. Columns: {list(df.columns)}")
        series = df[column]
        label = {"check": check, "column": column}

        if check == "not_null":
            mask = series.isna()
        elif check == "unique":
            mask = series.duplicated(keep=False) & series.notna()
        elif check == "numeric":
            mask = series.notna() & pd.to_numeric(series, errors="coerce").isna()
        elif check == "range":
            if "min" not in rule and "max" not in rule:
                raise ValueError("check 'range' requires 'min' and/or 'max'")
            numeric = pd.to_numeric(series, errors="coerce")
            mask = pd.Series(False, index=df.index)
            if "min" in rule:
                mask |= numeric < float(rule["min"])
            if "max" in rule:
                mask |= numeric > float(rule["max"])
        else:  # allowed
            values = rule.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError("check 'allowed' requires a non-empty 'values' list")
            mask = series.notna() & ~series.isin(values)

    violations = pd.Series(mask, index=df.index).fillna(False)
    n = int(violations.sum())
    return {
        **label,
        "description": rule.get("description"),
        "passed": n == 0,
        "n_violations": n,
        "violation_rate": round(float(violations.mean()), 4),
        "samples": df.loc[violations].head(SAMPLE_LIMIT).to_dict(orient="records")
        if n
        else [],
    }


def validate_data(path: str | Path, rules: list[dict[str, Any]] | None = None) -> dict:
    """Evaluate quality rules against a CSV and return a pass/fail report."""
    df = pd.read_csv(path)
    if rules is None:
        rules = [{"check": "not_null", "column": c} for c in df.columns]
        rules.append({"check": "no_duplicates"})
    if not isinstance(rules, list):
        raise ValueError("'rules' must be a list of rule objects")

    results = [_evaluate(df, rule) for rule in rules]
    n_failed = sum(1 for r in results if not r["passed"])
    return {
        "passed": n_failed == 0,
        "rows": int(len(df)),
        "n_rules": len(results),
        "n_failed": n_failed,
        "results": results,
    }
