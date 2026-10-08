from app.services.llm import (
    DEFAULT_TIMEOUT,
    LLMConfig,
    LLMService,
    _build_request,
    _parse_response,
)


def test_config_constructor_args():
    cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4-5", api_key="sk-test")
    svc = LLMService(api_key="sk-test", model_name="my-model", provider="openai")
    assert svc.config.model == "my-model"
    assert svc.config.provider == "openai"
    assert svc.available
    assert cfg.provider == "anthropic"


def test_unavailable_without_key():
    svc = LLMService(api_key="", model_name="x", provider="openai")
    assert not svc.available
    assert "not configured" in svc.complete("hello")


def test_timeout_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "150")
    assert LLMConfig.from_env().timeout == 150.0
    monkeypatch.delenv("LLM_TIMEOUT")
    assert LLMConfig.from_env().timeout == DEFAULT_TIMEOUT


def test_openai_request():
    cfg = LLMConfig(provider="openai", model="m", api_key="k")
    url, headers, payload = _build_request(cfg, [{"role": "user", "content": "hi"}])
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer k"
    assert payload["model"] == "m"


def test_openai_compatible_request():
    cfg = LLMConfig(
        provider="openai_compatible", model="llama3", api_key="",
        base_url="http://localhost:11434/v1",
    )
    url, headers, payload = _build_request(cfg, [{"role": "user", "content": "hi"}])
    assert url == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in headers


def test_anthropic_request_extracts_system():
    cfg = LLMConfig(provider="anthropic", model="claude-x", api_key="k")
    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    url, headers, payload = _build_request(cfg, messages)
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "k"
    assert payload["system"] == "be brief"
    assert payload["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    ]


def test_google_request():
    cfg = LLMConfig(provider="google", model="models/gemini-2.0-flash", api_key="k")
    url, headers, payload = _build_request(
        cfg, [{"role": "system", "content": "s"}, {"role": "assistant", "content": "a"}]
    )
    assert url.endswith("/models/gemini-2.0-flash:generateContent")
    assert headers["x-goog-api-key"] == "k"
    assert payload["contents"][0]["role"] == "model"
    assert payload["systemInstruction"]["parts"][0]["text"] == "s"


def test_parse_responses():
    assert _parse_response(
        "openai", {"choices": [{"message": {"content": "yo"}}]}
    ) == "yo"
    assert _parse_response(
        "anthropic", {"content": [{"type": "text", "text": "a"},
                                  {"type": "text", "text": "b"}]}
    ) == "ab"
    assert _parse_response(
        "google", {"candidates": [{"content": {"parts": [{"text": "g"}]}}]}
    ) == "g"


def test_unknown_provider_raises():
    import pytest

    cfg = LLMConfig(provider="nope", model="m", api_key="k")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        _build_request(cfg, [{"role": "user", "content": "hi"}])
