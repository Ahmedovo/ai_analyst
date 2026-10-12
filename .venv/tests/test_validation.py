"""Tests for the validate_data tool and the answer-grounding check."""

import json
from pathlib import Path

import pandas as pd
import pytest

from app.agents.grounding import extract_numbers, validate_answer
from app.tools.registry import run_tool

DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


# ---------------------------------------------------------------------------
# validate_data tool
# ---------------------------------------------------------------------------

def test_default_rules_pass_on_clean_data():
    out = json.loads(run_tool("validate_data", {}, DATA))
    assert out["passed"] is True
    assert out["n_failed"] == 0
    # one not_null rule per column + duplicate check
    assert out["n_rules"] == 7


def test_failing_rules_report_offenders(tmp_path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame(
        {"name": ["a", "b", None], "score": [10, -5, 200]}
    ).to_csv(bad, index=False)

    out = json.loads(
        run_tool(
            "validate_data",
            {
                "rules": [
                    {"check": "not_null", "column": "name"},
                    {"check": "range", "column": "score", "min": 0, "max": 100},
                ]
            },
            bad,
        )
    )
    assert out["passed"] is False
    assert out["n_failed"] == 2
    null_rule = out["results"][0]
    assert null_rule["n_violations"] == 1
    assert pd.isna(null_rule["samples"][0]["name"])
    range_rule = out["results"][1]
    assert range_rule["n_violations"] == 2  # -5 and 200


def test_allowed_unique_expression_checks(tmp_path):
    df = tmp_path / "d.csv"
    pd.DataFrame(
        {
            "region": ["North", "North", "East"],
            "id": [1, 1, 2],
            "units": [5, 3, 10],
            "price": [2.0, 2.0, 3.0],
        }
    ).to_csv(df, index=False)

    out = json.loads(
        run_tool(
            "validate_data",
            {
                "rules": [
                    {"check": "allowed", "column": "region", "values": ["South", "East"]},
                    {"check": "unique", "column": "id"},
                    {"check": "no_duplicates"},
                    {"check": "expression",
                     "expr": "units * price >= 10",  # row 1 (5*2) violates
                     "description": "revenue must be >= 10"},
                ]
            },
            df,
        )
    )
    assert out["passed"] is False
    checks = [r["check"] for r in out["results"]]
    assert checks == ["allowed", "unique", "no_duplicates", "expression"]
    assert out["results"][0]["n_violations"] == 2  # North not in allowed set
    assert out["results"][1]["n_violations"] == 2  # duplicated id=1
    assert out["results"][3]["n_violations"] == 1
    assert out["results"][3]["description"] == "revenue must be >= 10"


def test_validation_errors_surface_as_messages():
    with pytest.raises(ValueError, match="Unknown check"):
        run_tool("validate_data", {"rules": [{"check": "magic"}]}, DATA)
    with pytest.raises(ValueError, match="requires a 'column'"):
        run_tool("validate_data", {"rules": [{"check": "not_null"}]}, DATA)
    with pytest.raises(ValueError, match="not found"):
        run_tool("validate_data", {"rules": [{"check": "not_null", "column": "zzz"}]}, DATA)
    with pytest.raises(ValueError, match="Invalid expression"):
        run_tool("validate_data",
                 {"rules": [{"check": "expression", "expr": "not a condition >>>"}]}, DATA)


# ---------------------------------------------------------------------------
# grounding (answer validation)
# ---------------------------------------------------------------------------

def test_extract_numbers():
    assert extract_numbers("Revenue was 1,183.72 (12.5%) in Q3") == [
        "1,183.72", "12.5%",
    ]
    assert extract_numbers("compare v2 vs v10 and Q3") == []
    assert extract_numbers(None) == []


def test_extract_numbers_folds_unicode_punctuation():
    # narrow no-break space as thousands separator + U+2212 minus sign
    assert extract_numbers("mean 1\u202f183.7225, corr \u22120.814") == [
        "1,183.7225",
        "-0.814",
    ]


def test_unicode_separators_are_grounded():
    steps = [{"result": "mean 1,183.7225\ncorrelation -0.8137"}]
    answer = "Mean is 1\u202f183.7225 with correlation \u22120.814."
    verdict = validate_answer(answer, steps)
    assert verdict["passed"] is True, verdict["unsupported"]
    assert verdict["unsupported"] == []


def test_display_rounding_is_grounded():
    # tool results keep full precision; the answer shows rounded values
    steps = [{"result": "rate 0.27480381881255583\nmean 1183.7225"}]
    verdict = validate_answer("The rate is 0.275 and the mean is 1,184.", steps)
    assert verdict["passed"] is True, verdict["unsupported"]


def test_percent_grounded_against_fraction_rate():
    steps = [{"result": "anomaly_rate 0.05"}]
    verdict = validate_answer("5% of the rows look anomalous.", steps)
    assert verdict["passed"] is True, verdict["unsupported"]


def test_materially_wrong_numbers_still_flagged():
    steps = [{"result": "rows 20 total 23674.45"}]
    verdict = validate_answer("There are 21 rows totalling 23,700.", steps)
    assert verdict["passed"] is False
    assert verdict["unsupported"] == ["21", "23,700"]


def test_grounded_answer_passes():
    steps = [{"result": "total 23674.45\nrows 20"}]
    verdict = validate_answer("Total revenue is 23,674.45 across 20 rows.", steps)
    assert verdict["passed"] is True
    assert verdict["checked"] == 2
    assert verdict["unsupported"] == []


def test_hallucinated_number_is_flagged():
    steps = [{"result": "total 23674.45"}]
    verdict = validate_answer("Revenue was 23,674.45, up 42% year over year.", steps)
    assert verdict["passed"] is False
    assert verdict["unsupported"] == ["42%"]


def test_question_numbers_are_accepted():
    steps = [{"result": "anything"}]
    verdict = validate_answer("In 2025 revenue fell.", steps, question="How was 2025?")
    assert verdict["passed"] is True
    assert verdict["checked"] == 0


def test_no_steps_passes_but_is_noted():
    verdict = validate_answer("42", [])
    assert verdict["passed"] is True
    assert "note" in verdict


def test_follow_up_number_grounded_by_prior_evidence():
    """No tools this turn — the number is reused from an earlier turn's tools."""
    verdict = validate_answer(
        "The mean revenue was 1183.72.",
        [],
        question="what was the mean revenue again?",
        prior_results=["mean revenue 1183.7225"],
    )
    assert verdict["passed"] is True
    assert verdict["unsupported"] == []
    assert verdict["tool_results"] == 0  # counts the current run's tools only


def test_follow_up_unknown_number_still_flagged():
    verdict = validate_answer(
        "There are 9999 rows.",
        [],
        prior_results=["rows 20"],
    )
    assert verdict["passed"] is False
    assert verdict["unsupported"] == ["9999"]
