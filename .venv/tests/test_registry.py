import json
from pathlib import Path

import pytest

from app.tools.registry import TOOL_DEFINITIONS, TOOL_FUNCTIONS, run_tool

DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


def test_definitions_match_functions():
    def_names = [t["name"] for t in TOOL_DEFINITIONS]
    assert def_names == list(TOOL_FUNCTIONS)  # same tools, same order
    assert len(def_names) == 7
    for t in TOOL_DEFINITIONS:
        assert t["description"]
        assert t["parameters"]["type"] == "object"


def test_profile_dataset():
    out = json.loads(run_tool("profile_dataset", {}, DATA))
    assert out["rows"] == 20
    assert "revenue" in out["dtypes"]


def test_execute_sql():
    out = run_tool("execute_sql", {"sql": "SELECT COUNT(*) AS n FROM {table}"}, DATA)
    assert "rows returned: 1" in out
    assert "20" in out


def test_group_by():
    out = run_tool(
        "group_by", {"by": ["region"], "values": ["revenue"], "agg": "sum"}, DATA
    )
    assert "region" in out and "revenue" in out
    assert "North" in out


def test_calculate_statistics():
    out = json.loads(run_tool("calculate_statistics", {"columns": ["revenue"]}, DATA))
    assert out["describe"]["revenue"]["count"] == 20


def test_detect_anomalies():
    out = json.loads(run_tool("detect_anomalies", {"column": "units"}, DATA))
    assert out["method"] == "iqr"
    assert "n_anomalies" in out
    assert isinstance(out["anomalies"], list)


def test_create_chart(tmp_path):
    out = run_tool(
        "create_chart",
        {"chart_type": "bar", "x": "region", "y": "revenue",
         "title": "Revenue by region", "output_name": "test_rev_by_region"},
        DATA,
    )
    assert out.endswith(".png")
    assert Path(out).exists()


def test_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        run_tool("does_not_exist", {}, DATA)


def test_bad_arguments_raise():
    with pytest.raises(ValueError):
        run_tool("group_by", {"by": ["nope"], "values": ["revenue"]}, DATA)
    with pytest.raises(ValueError):
        run_tool("detect_anomalies", {"column": "region"}, DATA)
    with pytest.raises(ValueError):
        run_tool("create_chart", {"chart_type": "pie"}, DATA)
