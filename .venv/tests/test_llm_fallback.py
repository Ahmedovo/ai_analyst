"""LLM fallback: when the primary provider fails, try the next one.

Covers the real reason this exists — an exhausted (free) daily quota on the
primary provider must not end the run when a second provider is configured.
"""

from unittest.mock import MagicMock

import pytest

from app.services import llm as llm_module
from app.services.llm import LLMConfig, LLMService


class FakeResp:
    def __init__(self, status: int, text: str = "", headers: dict | None = None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def json(self) -> dict:
        import json as _json

        return _json.loads(self.text)


def _primary(**overrides) -> LLMConfig:
    return LLMConfig(provider="openai", model="primary", api_key="k1", **overrides)


def _backup(**overrides) -> LLMConfig:
    values = dict(
        provider="openai_compatible",
        model="backup",
        api_key="k2",
        base_url="https://api.groq.com/openai/v1",
    )
    values.update(overrides)
    return LLMConfig(**values)


def test_falls_back_when_primary_quota_exhausted(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "openai.com" in url:
            return FakeResp(429, '{"error": {"message": "free-models-per-day quota"}}')
        return FakeResp(200, '{"choices": [{"message": {"content": "from fallback"}}]}')

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    monkeypatch.setattr(llm_module.time, "sleep", lambda _s: None)

    svc = LLMService(config=_primary(max_retries=2), fallbacks=[_backup()])
    result = svc.chat([{"role": "user", "content": "hi"}])

    assert result.text == "from fallback"
    # the answer records which provider actually served it
    assert result.provider == "openai_compatible"
    assert result.model == "backup"
    assert sum("openai.com" in u for u in calls) == 3  # primary retried first
    assert any("groq.com" in u for u in calls)


def test_primary_success_skips_fallback(monkeypatch):
    post = MagicMock(
        return_value=FakeResp(200, '{"choices": [{"message": {"content": "ok"}}]}')
    )
    monkeypatch.setattr(llm_module.httpx, "post", post)

    svc = LLMService(config=_primary(), fallbacks=[_backup()])
    assert svc.chat([{"role": "user", "content": "hi"}]).text == "ok"
    assert post.call_count == 1
    assert "api.openai.com" in post.call_args.args[0]


def test_all_providers_failing_raises(monkeypatch):
    post = MagicMock(return_value=FakeResp(429, '"quota"'))
    monkeypatch.setattr(llm_module.httpx, "post", post)
    monkeypatch.setattr(llm_module.time, "sleep", lambda _s: None)

    svc = LLMService(
        config=_primary(max_retries=0),
        fallbacks=[LLMConfig(provider="anthropic", model="backup", api_key="k2", max_retries=0)],
    )
    with pytest.raises(RuntimeError) as err:
        svc.chat([{"role": "user", "content": "hi"}])

    message = err.value.args[0]
    assert message.startswith("All LLM providers failed")
    assert "openai/primary" in message
    assert "anthropic/backup" in message
    assert post.call_count == 2


def test_available_when_only_fallback_has_key():
    svc = LLMService(
        config=LLMConfig(provider="openai", model="m", api_key=""),
        fallbacks=[LLMConfig(provider="anthropic", model="b", api_key="k2")],
    )
    assert svc.available
    assert svc.providers == ["openai", "anthropic"]


def test_fallback_configs_from_env(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "gsk_x")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "llama-3.3-70b")
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_FALLBACK_2_PROVIDER", "google")
    monkeypatch.setenv("LLM_FALLBACK_2_API_KEY", "AIza")
    monkeypatch.setenv("LLM_FALLBACK_2_MODEL", "gemini-2.0-flash")

    configs = LLMConfig.fallback_configs_from_env()

    assert [c.provider for c in configs] == ["openai_compatible", "google"]
    assert configs[0].base_url == "https://api.groq.com/openai/v1"
    assert configs[0].model == "llama-3.3-70b"
    assert configs[0].api_key == "gsk_x"
    assert configs[1].model == "gemini-2.0-flash"


def test_fallback_env_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)

    assert LLMConfig.fallback_configs_from_env() == []


def test_service_reads_env_fallbacks_when_built_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "primary-key")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "fallback-key")

    svc = LLMService()

    assert svc.providers == ["openai", "anthropic"]


def test_explicit_config_ignores_env_fallbacks(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "fallback-key")

    svc = LLMService(config=LLMConfig(provider="openai", model="m", api_key="k"))

    assert svc.fallbacks == []
