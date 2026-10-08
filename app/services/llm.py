"""Provider-agnostic LLM service with native tool (function) calling.

Supports any provider via plain HTTP, no vendor SDK:

- ``openai``          — OpenAI API (api.openai.com/v1)
- ``openai_compatible`` — any OpenAI-compatible endpoint (OpenRouter, Groq,
  Together, LM Studio, vLLM, Ollama's /v1, ...) via ``base_url``
- ``anthropic``       — Claude Messages API
- ``google``          — Gemini generateContent API

Tool calls are normalised across providers: ``chat(messages, tools=...)``
returns a :class:`ChatResponse` with plain text and/or parsed
:class:`ToolCall` entries, regardless of provider wire format.

Configure with constructor args (``api_key``, ``model_name``, ...) or env vars:

    LLM_PROVIDER=openai_compatible
    LLM_API_KEY=sk-...
    LLM_MODEL=qwen2.5:14b
    LLM_BASE_URL=http://localhost:11434/v1
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TIMEOUT = 60.0

#: Neutral tool definition: ``{name, description, parameters}`` (JSON Schema).
ToolDefinition = dict[str, Any]


@dataclass
class LLMConfig:
    """Connection settings for any LLM provider."""

    provider: str = "openai"  # openai | openai_compatible | anthropic | google
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls, **overrides: Any) -> "LLMConfig":
        """Build config from environment variables, with keyword overrides."""
        values: dict[str, Any] = {
            "provider": os.getenv("LLM_PROVIDER")
            or ("openai_compatible" if os.getenv("OPENAI_BASE_URL") else "openai"),
            "model": os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            "api_key": os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2048")),
            "timeout": float(os.getenv("LLM_TIMEOUT", str(DEFAULT_TIMEOUT))),
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)


@dataclass
class ToolCall:
    """A model-requested tool invocation, normalised across providers."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Result of one model turn: optional text and zero or more tool calls."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------

def _is_openai_family(provider: str) -> bool:
    return provider.lower() in ("openai", "openai_compatible", "compatible", "ollama")


def _is_anthropic(provider: str) -> bool:
    return provider.lower() in ("anthropic", "claude")


def _is_google(provider: str) -> bool:
    return provider.lower() in ("google", "gemini", "vertex")


# ---------------------------------------------------------------------------
# Conversation conversion: neutral messages -> provider wire format
# ---------------------------------------------------------------------------
#
# Neutral message shapes:
#   {"role": "system" | "user", "content": str}
#   {"role": "assistant", "content": str | None, "tool_calls": [{id, name, arguments}]}
#   {"role": "tool", "tool_call_id": str, "name": str, "content": str}


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role in ("system", "user"):
            out.append({"role": role, "content": m["content"]})
        elif role == "assistant":
            item: dict[str, Any] = {"role": "assistant", "content": m.get("content")}
            if m.get("tool_calls"):
                item["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("arguments") or {}),
                        },
                    }
                    for c in m["tool_calls"]
                ]
            out.append(item)
        elif role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m["tool_call_id"],
                    "name": m.get("name", ""),
                    "content": m["content"],
                }
            )
    return out


def _to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(system_text, messages)`` in Anthropic wire format."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m["content"])
            continue
        blocks: list[dict[str, Any]] = []
        if role == "tool":
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": m["tool_call_id"],
                    "content": m["content"],
                }
            )
            role = "user"
        elif role == "user":
            blocks.append({"type": "text", "text": m["content"]})
        else:  # assistant
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for c in m.get("tool_calls") or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": c["id"],
                        "name": c["name"],
                        "input": c.get("arguments") or {},
                    }
                )
        # Anthropic requires alternating roles: merge adjacent same-role messages.
        if converted and converted[-1]["role"] == role:
            converted[-1]["content"].extend(blocks)
        else:
            converted.append({"role": role, "content": blocks})
    return "\n".join(system_parts), converted


def _to_google_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(system_text, contents)`` in Gemini wire format."""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m["content"])
            continue
        parts: list[dict[str, Any]] = []
        if role == "tool":
            g_role = "user"
            parts.append(
                {
                    "functionResponse": {
                        "name": m.get("name") or "tool",
                        "response": {"result": m["content"]},
                    }
                }
            )
        elif role == "assistant":
            g_role = "model"
            if m.get("content"):
                parts.append({"text": m["content"]})
            for c in m.get("tool_calls") or []:
                parts.append(
                    {"functionCall": {"name": c["name"], "args": c.get("arguments") or {}}}
                )
        else:
            g_role = "user"
            parts.append({"text": m["content"]})
        if contents and contents[-1]["role"] == g_role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": g_role, "parts": parts})
    return "\n".join(system_parts), contents


# ---------------------------------------------------------------------------
# Tool schema wrapping per provider
# ---------------------------------------------------------------------------

def _wrap_tools(provider: str, tools: list[ToolDefinition]) -> Any:
    """Wrap neutral tool definitions into each provider's wire format."""
    if _is_openai_family(provider):
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]
    if _is_anthropic(provider):
        return [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]
    if _is_google(provider):
        return [
            {
                "functionDeclarations": [
                    {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    }
                    for t in tools
                ]
            }
        ]
    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        "Use one of: openai, openai_compatible, anthropic, google."
    )


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------

def _build_request(
    cfg: LLMConfig,
    messages: list[dict[str, Any]],
    tools: list[ToolDefinition] | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Return ``(url, headers, json_payload)`` for the configured provider."""
    provider = cfg.provider

    if _is_openai_family(provider):
        base = cfg.base_url or "https://api.openai.com/v1"
        url = f"{base.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
        lower = base.lower()
        if "openrouter.ai" in lower:
            headers.setdefault("HTTP-Referer", "http://localhost:5174")
            headers.setdefault("X-Title", "AI Data Analyst")
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": _to_openai_messages(messages),
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
        if tools:
            payload["tools"] = _wrap_tools(provider, tools)
            payload["tool_choice"] = "auto"
        return url, headers, payload

    if _is_anthropic(provider):
        base = cfg.base_url or "https://api.anthropic.com"
        url = f"{base.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        system, anth_messages = _to_anthropic_messages(messages)
        payload = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "messages": anth_messages,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = _wrap_tools(provider, tools)
        return url, headers, payload

    if _is_google(provider):
        base = cfg.base_url or "https://generativelanguage.googleapis.com/v1beta"
        model = cfg.model.removeprefix("models/")
        url = f"{base.rstrip('/')}/models/{model}:generateContent"
        headers = {"x-goog-api-key": cfg.api_key}
        system, contents = _to_google_messages(messages)
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": cfg.temperature,
                "maxOutputTokens": cfg.max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = _wrap_tools(provider, tools)
        return url, headers, payload

    raise ValueError(
        f"Unknown LLM provider '{cfg.provider}'. "
        "Use one of: openai, openai_compatible, anthropic, google."
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(provider: str, data: dict[str, Any]) -> str:
    """Extract the text completion from a provider response body."""
    provider = provider.lower()

    if _is_openai_family(provider):
        choices = data.get("choices") or []
        if not choices:
            err = data.get("error") or {}
            msg = err.get("message") or data.get("message") or "unknown error"
            return f"[LLM error: {msg}]"
        message = (choices[0] or {}).get("message", {}) or {}
        return message.get("content") or ""

    if _is_anthropic(provider):
        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

    if _is_google(provider):
        candidates = data.get("candidates") or [{}]
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if "text" in p)

    raise ValueError(f"Unknown LLM provider '{provider}'.")


def _parse_tool_calls(provider: str, data: dict[str, Any]) -> list[ToolCall]:
    """Extract normalised tool calls from a provider response body."""
    provider = provider.lower()
    calls: list[ToolCall] = []

    if _is_openai_family(provider):
        choices = data.get("choices") or []
        if not choices:
            return calls
        message = (choices[0] or {}).get("message", {}) or {}
        for tc in (message.get("tool_calls") or []):
            fn = (tc or {}).get("function", {}) or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {"_raw": raw_args}
            calls.append(
                ToolCall(id=(tc or {}).get("id") or f"call_{uuid.uuid4().hex[:8]}",
                         name=fn.get("name", ""), arguments=args)
            )
        return calls

    if _is_anthropic(provider):
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                calls.append(
                    ToolCall(id=block.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                             name=block.get("name", ""),
                             arguments=block.get("input") or {})
                )
        return calls

    if _is_google(provider):
        candidates = data.get("candidates") or [{}]
        parts = candidates[0].get("content", {}).get("parts", [])
        for i, part in enumerate(parts):
            fc = part.get("functionCall")
            if fc:
                calls.append(
                    ToolCall(id=f"call_{i}_{uuid.uuid4().hex[:8]}",
                             name=fc.get("name", ""),
                             arguments=fc.get("args") or {})
                )
        return calls

    raise ValueError(f"Unknown LLM provider '{provider}'.")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LLMService:
    """Minimal chat-completion client with tool calling, provider-agnostic."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        config: LLMConfig | None = None,
    ) -> None:
        self.config = config or LLMConfig.from_env(
            api_key=api_key, model=model_name, provider=provider, base_url=base_url
        )

    @property
    def available(self) -> bool:
        return bool(self.config.api_key)

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Send a single-turn prompt and return the completion text."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages).text

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        """Send a conversation (optionally with tools) and get one model turn."""
        cfg = self.config
        if not cfg.api_key:
            return ChatResponse(
                text=f"[LLM not configured: set LLM_API_KEY for provider '{cfg.provider}']"
            )

        url, headers, payload = _build_request(cfg, messages, tools)
        response = httpx.post(url, json=payload, headers=headers, timeout=cfg.timeout)
        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM request failed ({response.status_code}): {response.text[:500]}"
            )
        data = response.json()
        return ChatResponse(
            text=_parse_response(cfg.provider, data),
            tool_calls=_parse_tool_calls(cfg.provider, data),
        )
