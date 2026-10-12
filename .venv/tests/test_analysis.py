from pathlib import Path

from app.tools.profiler import profile_dataframe
from app.tools.statistics import describe_statistics

DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


def test_profile_shape():
    profile = profile_dataframe(DATA)
    assert profile["rows"] == 20
    assert "revenue" in profile["dtypes"]


def test_statistics():
    stats = describe_statistics(DATA)
    assert "describe" in stats
    assert "revenue" in stats["describe"]
