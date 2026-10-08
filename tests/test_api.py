"""API tests — offline via an injected agent with a scripted fake LLM."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.analyst import AnalystAgent
from app.api.main import create_app
from app.services.llm import ChatResponse, ToolCall

DATA = Path(__file__).resolve().parents[1] / "data"
CHARTS = Path(__file__).resolve().parents[1] / "generated" / "charts"


class FakeLLM:
    """Returns scripted responses in order (repeats the last one)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        response = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        return response


@pytest.fixture()
def client():
    fake = FakeLLM(
        [
            ChatResponse(
                text="Profiling first.",
                tool_calls=[ToolCall(id="c1", name="profile_dataset", arguments={})],
            ),
            ChatResponse(text="The dataset has 20 rows."),
        ]
    )
    app = create_app(agent=AnalystAgent(llm=fake))
    return TestClient(app)


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def test_root(client):
    body = client.get("/").json()
    assert body["title"] == "AI Data Analyst API"
    assert body["docs"] == "/docs"


def test_health_does_not_leak_key(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["provider"] and body["model"]
    assert "api_key" not in str(body).lower()


def test_tools_endpoint_lists_seven(client):
    body = client.get("/api/tools").json()
    assert body["count"] == 7
    names = [t["name"] for t in body["tools"]]
    assert "validate_data" in names and "execute_sql" in names
    assert all(t["parameters"]["type"] == "object" for t in body["tools"])


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def test_datasets_lists_sales(client):
    names = [d["name"] for d in client.get("/api/datasets").json()]
    assert "sales.csv" in names


def test_upload_csv_roundtrip(client):
    content = b"a,b\n1,2\n3,4\n"
    try:
        r = client.post(
            "/api/datasets",
            files={"file": ("api_upload.csv", content, "text/csv")},
        )
        assert r.status_code == 200
        assert r.json() == {"name": "api_upload.csv", "size": len(content)}

        names = [d["name"] for d in client.get("/api/datasets").json()]
        assert "api_upload.csv" in names
    finally:
        (DATA / "api_upload.csv").unlink(missing_ok=True)


def test_upload_rejects_non_csv(client):
    r = client.post("/api/datasets", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_upload_rejects_empty(client):
    r = client.post("/api/datasets", files={"file": ("empty.csv", b"", "text/csv")})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def test_analyze_end_to_end(client):
    r = client.post(
        "/api/analyze",
        json={"dataset": "sales.csv", "question": "How many rows does this have?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dataset"] == "sales.csv"  # echoed as requested, not an FS path
    assert body["answer"] == "The dataset has 20 rows."
    assert body["steps"][0]["tool"] == "profile_dataset"
    assert body["steps"][0]["status"] == "ok"
    assert body["validation"]["passed"] is True


def test_analyze_unknown_dataset_404(client):
    r = client.post("/api/analyze", json={"dataset": "ghost.csv", "question": "how much?"})
    assert r.status_code == 404


def test_analyze_path_traversal_400(client):
    r = client.post(
        "/api/analyze",
        json={"dataset": "../requirements.txt", "question": "how much?"},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/analyze",
        json={"dataset": "..\\..\\secrets.csv", "question": "how much?"},
    )
    assert r.status_code == 400


def test_analyze_validation_errors_422(client):
    assert client.post("/api/analyze", json={"dataset": "sales.csv"}).status_code == 422
    assert (
        client.post(
            "/api/analyze",
            json={"dataset": "sales.csv", "question": "x", "max_turns": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/analyze",
            json={"dataset": "sales.csv", "question": "q", "max_turns": 99},
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def test_chart_roundtrip(client):
    CHARTS.mkdir(parents=True, exist_ok=True)
    fake_png = CHARTS / "api_test_chart.png"
    fake_png.write_bytes(b"\x89PNG fake")
    try:
        names = client.get("/api/charts").json()["charts"]
        assert "api_test_chart.png" in names
        r = client.get("/api/charts/api_test_chart.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content == b"\x89PNG fake"
    finally:
        fake_png.unlink(missing_ok=True)


def test_chart_traversal_blocked(client):
    assert client.get("/api/charts/..%5C..%5C.env.png").status_code in (400, 404)
    assert client.get("/api/charts/nope.png").status_code == 404


# ---------------------------------------------------------------------------
# Streaming (NDJSON)
# ---------------------------------------------------------------------------

def _read_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        if line.strip():
            events.append(json.loads(line))
    return events


def test_analyze_stream_emits_live_events(client):
    with client.stream(
        "POST",
        "/api/analyze/stream",
        json={"dataset": "sales.csv", "question": "How many rows?"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-ndjson")
        events = _read_events(r)

    types = [e["type"] for e in events]
    # node events for the whole loop, one tool step, validation, final result
    assert types[0] == "node"
    assert {"node", "plan", "step", "validation", "done"} <= set(types)
    assert [e["node"] for e in events if e["type"] == "node"].count("tools") == 1

    step = next(e for e in events if e["type"] == "step")
    assert step["step"]["tool"] == "profile_dataset"

    plan = next(e for e in events if e["type"] == "plan")
    assert plan["text"] == "Profiling first."

    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["answer"] == "The dataset has 20 rows."
    assert done["result"]["dataset"] == "sales.csv"  # name echoed, not a path
    assert done["result"]["validation"]["passed"] is True


def test_analyze_stream_rejects_bad_dataset(client):
    r = client.post(
        "/api/analyze/stream",
        json={"dataset": "../etc.csv", "question": "how much?"},
    )
    assert r.status_code == 400


def test_analyze_stream_survives_agent_crash():
    """A mid-run crash must surface as an `error` event, not a dead socket."""

    class ExplodingAgent:
        def stream(self, dataset, question, max_turns):
            raise RuntimeError("upstream exploded")
            yield  # pragma: no cover — makes this a generator function

    client = TestClient(create_app(agent=ExplodingAgent()))
    with client.stream(
        "POST",
        "/api/analyze/stream",
        json={"dataset": "sales.csv", "question": "boom"},
    ) as r:
        assert r.status_code == 200
        events = _read_events(r)

    assert [e["type"] for e in events] == ["error"]
    assert "upstream exploded" in events[0]["message"]


def test_analyze_wraps_agent_failure_as_502():
    class ExplodingAgent:
        def analyze(self, dataset, question, max_turns):
            raise RuntimeError("upstream exploded")

    client = TestClient(create_app(agent=ExplodingAgent()))
    r = client.post(
        "/api/analyze",
        json={"dataset": "sales.csv", "question": "boom"},
    )
    assert r.status_code == 502
    assert "upstream exploded" in r.json()["detail"]
