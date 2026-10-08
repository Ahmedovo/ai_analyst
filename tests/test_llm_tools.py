"""Tool-calling wire format: request building and response parsing per provider."""

from app.services.llm import (
    LLMConfig,
    _build_request,
    _parse_response,
    _parse_tool_calls,
    _wrap_tools,
)

TOOLS = [
    {
        "name": "profile_dataset",
        "description": "Profile the dataset.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "execute_sql",
        "description": "Run SQL.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
]

CONVERSATION = [
    {"role": "system", "content": "be rigorous"},
    {"role": "user", "content": "why did revenue drop?"},
    {
        "role": "assistant",
        "content": "Profiling first.",
        "tool_calls": [{"id": "c1", "name": "profile_dataset", "arguments": {}}],
    },
    {"role": "tool", "tool_call_id": "c1", "name": "profile_dataset", "content": "{\"rows\": 20}"},
]


def test_openai_request_with_tools():
    cfg = LLMConfig(provider="openai", model="m", api_key="k")
    _, _, payload = _build_request(cfg, CONVERSATION, TOOLS)
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["function"]["name"] == "profile_dataset"
    assert payload["tool_choice"] == "auto"
    # history round-trips: assistant tool_calls serialised as JSON string
    asst = payload["messages"][2]
    assert asst["tool_calls"][0]["function"]["arguments"] == "{}"
    assert payload["messages"][3] == {
        "role": "tool", "tool_call_id": "c1", "name": "profile_dataset",
        "content": "{\"rows\": 20}",
    }


def test_anthropic_request_with_tools():
    cfg = LLMConfig(provider="anthropic", model="m", api_key="k")
    _, _, payload = _build_request(cfg, CONVERSATION, TOOLS)
    assert payload["system"] == "be rigorous"
    assert payload["tools"][0]["input_schema"]["type"] == "object"
    assert "tool_result" in str(payload["messages"][2])  # tool result block
    asst_blocks = payload["messages"][1]["content"]
    assert any(b["type"] == "tool_use" and b["input"] == {} for b in asst_blocks)


def test_google_request_with_tools():
    cfg = LLMConfig(provider="google", model="gemini-2.0-flash", api_key="k")
    url, _, payload = _build_request(cfg, CONVERSATION, TOOLS)
    assert "functionDeclarations" in payload["tools"][0]
    assert payload["systemInstruction"]["parts"][0]["text"] == "be rigorous"
    assert url.endswith(":generateContent")
    flat = str(payload["contents"])
    assert "functionCall" in flat and "functionResponse" in flat


def test_wrap_tools_unknown_provider():
    import pytest

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        _wrap_tools("nope", TOOLS)


def test_parse_openai_tool_calls():
    data = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "c1", "type": "function",
                         "function": {"name": "execute_sql",
                                      "arguments": "{\"sql\": \"SELECT 1\"}"}}
                    ],
                }
            }
        ]
    }
    calls = _parse_tool_calls("openai", data)
    assert len(calls) == 1
    assert calls[0].id == "c1"
    assert calls[0].arguments == {"sql": "SELECT 1"}
    assert _parse_response("openai", data) == ""


def test_parse_anthropic_tool_calls():
    data = {
        "content": [
            {"type": "text", "text": "Plan: profile first."},
            {"type": "tool_use", "id": "t1", "name": "profile_dataset", "input": {}},
        ]
    }
    calls = _parse_tool_calls("anthropic", data)
    assert calls[0].id == "t1"
    assert _parse_response("anthropic", data) == "Plan: profile first."


def test_parse_google_tool_calls():
    data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "checking"},
                        {"functionCall": {"name": "group_by",
                                          "args": {"by": ["region"], "values": ["revenue"]}}},
                    ]
                }
            }
        ]
    }
    calls = _parse_tool_calls("google", data)
    assert calls[0].name == "group_by"
    assert calls[0].arguments["by"] == ["region"]
    assert _parse_response("google", data) == "checking"


def test_parse_openai_malformed_arguments_survives():
    data = {
        "choices": [
            {"message": {"tool_calls": [
                {"id": "c", "function": {"name": "x", "arguments": "{broken"}}
            ]}}
        ]
    }
    calls = _parse_tool_calls("openai", data)
    assert "_raw" in calls[0].arguments
