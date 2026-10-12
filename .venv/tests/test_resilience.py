"""Resilience: transient LLM failures must never leave the user without an answer."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.analyst import AnalystAgent
from app.services import llm as llm_module
from app.services.llm import ChatResponse, LLMConfig, LLMService, ToolCall

DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


class CrashesAfterFirst:
    """One successful tool-calling turn, then the provider dies mid-run."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="execute_sql",
                        arguments={
                            "sql": "SELECT region, SUM(revenue) AS revenue FROM {table} GROUP BY region"
                        },
                    )
                ]
            )
        raise RuntimeError("LLM request failed (429): rate limit exceeded")


def test_analyze_survives_llm_crash_with_evidence_digest():
    """A mid-run provider failure produces a grounded evidence digest, not a crash."""
    agent = AnalystAgent(llm=CrashesAfterFirst())
    result = agent.analyze(DATA, "total revenue by region")

    assert result.answer
    assert "Analysis interrupted" in result.answer
    assert "execute_sql" in result.answer
    assert result.validation  # grounded once; never raises
    assert result.steps


def test_stream_survives_llm_crash_and_emits_done():
    """The stream keeps delivering a `done` event (with the digest) instead of
    dying with an `error` event — the frontend always gets an answer."""
    agent = AnalystAgent(llm=CrashesAfterFirst())
    events = list(agent.stream(DATA, "total revenue by region"))

    types = [e["type"] for e in events]
    assert types[-1] == "done"
    assert "error" not in types
    assert "step" in types
    assert "Analysis interrupted" in events[-1]["result"]["answer"]


class FakeResp:
    def __init__(self, status: int, text: str = "", headers: dict | None = None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def json(self) -> dict:
        import json as _json

        return _json.loads(self.text)


def _svc(**overrides) -> LLMService:
    cfg = LLMConfig(
        provider="openai", model="m", api_key="k", max_retries=2, **overrides
    )
    return LLMService(config=cfg)


def test_llm_retries_transient_then_raises_clean_error(monkeypatch):
    post = MagicMock(
        return_value=FakeResp(429, '{"error": {"message": "free-models-per-day quota"}}')
    )
    monkeypatch.setattr(llm_module.httpx, "post", post)
    monkeypatch.setattr(llm_module.time, "sleep", lambda _s: None)

    svc = _svc()
    with pytest.raises(RuntimeError) as err:
        svc.chat([{"role": "user", "content": "hi"}])

    assert err.value.args[0].startswith("LLM request failed (429):")
    assert "quota" in err.value.args[0]
    assert post.call_count == 3  # initial + 2 retries
    # raw provider JSON must never leak into the message
    assert '"error"' not in err.value.args[0]


def test_llm_recovers_on_retry(monkeypatch):
    post = MagicMock(
        side_effect=[
            FakeResp(503, "gateway hiccup"),
            FakeResp(200, '{"choices": [{"message": {"content": "yo"}}]}'),
        ]
    )
    monkeypatch.setattr(llm_module.httpx, "post", post)
    monkeypatch.setattr(llm_module.time, "sleep", lambda _s: None)

    result = _svc().chat([{"role": "user", "content": "hi"}])
    assert result.text == "yo"
    assert post.call_count == 2


def test_llm_non_transient_error_not_retried(monkeypatch):
    post = MagicMock(return_value=FakeResp(401, '{"error": {"message": "bad key"}}'))
    monkeypatch.setattr(llm_module.httpx, "post", post)

    svc = _svc()
    with pytest.raises(RuntimeError, match=r"LLM request failed \(401\)"):
        svc.chat([{"role": "user", "content": "hi"}])

    assert post.call_count == 1
