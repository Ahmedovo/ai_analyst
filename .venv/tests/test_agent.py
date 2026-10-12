"""Agent loop tests using a scripted fake LLM (no API key needed)."""

from pathlib import Path

from app.agents.analyst import AnalystAgent, build_system_prompt
from app.schemas.analysis import AnalysisResult
from app.services.llm import ChatResponse, ToolCall, LLMService
from app.tools.registry import TOOL_DEFINITIONS

DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


class FakeLLM:
    """Replays scripted responses and records the messages it was sent."""

    def __init__(self, script: list[ChatResponse]):
        self.script = list(script)
        self.calls: list[dict] = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.script.pop(0)


def test_system_prompt_lists_tools():
    prompt = build_system_prompt(max_turns=5)
    assert "You are an autonomous data analyst." in prompt
    assert "Never invent numerical results." in prompt
    assert "Batch independent calls" in prompt  # one response, many tools
    assert "at most 5 tool-calling turns" in prompt  # budget is visible to the model
    for t in TOOL_DEFINITIONS:
        assert t["name"] in prompt


def test_agent_plans_executes_and_answers():
    fake = FakeLLM(
        [
            ChatResponse(
                text="I'll start by profiling the dataset.",
                tool_calls=[ToolCall(id="c1", name="profile_dataset", arguments={})],
            ),
            ChatResponse(
                text="Now the revenue trend per region.",
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="execute_sql",
                        arguments={"sql": "SELECT region, SUM(revenue) AS total FROM {table} GROUP BY region"},
                    ),
                    ToolCall(
                        id="c3",
                        name="group_by",
                        arguments={"by": ["product"], "values": ["revenue"], "agg": "sum"},
                    ),
                ],
            ),
            ChatResponse(text="Revenue is concentrated in Widget B. Final answer."),
        ]
    )
    agent = AnalystAgent(llm=fake)
    result = agent.analyze(DATA, "Why did revenue decrease in Q3?")

    assert isinstance(result, AnalysisResult)
    assert result.answer == "Revenue is concentrated in Widget B. Final answer."
    assert [s["tool"] for s in result.steps] == [
        "profile_dataset", "execute_sql", "group_by",
    ]
    assert all(s["status"] == "ok" for s in result.steps)

    # Three model turns, each received the tool definitions.
    assert len(fake.calls) == 3
    assert all(c["tools"] == TOOL_DEFINITIONS for c in fake.calls)

    # Conversation grows correctly: system+user, then assistant+tool turns.
    roles = [m["role"] for m in fake.calls[2]["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "tool"]
    tool_msgs = [m for m in fake.calls[2]["messages"] if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in tool_msgs} == {"c1", "c2", "c3"}


def test_agent_reports_tool_errors_and_recovers():
    fake = FakeLLM(
        [
            ChatResponse(
                text="bad call",
                tool_calls=[ToolCall(id="c1", name="no_such_tool", arguments={})],
            ),
            ChatResponse(text="Recovered using available data."),
        ]
    )
    agent = AnalystAgent(llm=fake)
    result = agent.analyze(DATA, "anything")

    assert result.steps[0]["status"] == "error"
    assert result.steps[0]["result"].startswith("ERROR:")
    # The error was handed back to the model in a tool message.
    tool_msg = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["content"].startswith("ERROR:")
    assert result.answer == "Recovered using available data."


def test_agent_stops_at_max_turns():
    looping = FakeLLM(
        [
            ChatResponse(tool_calls=[ToolCall(id=f"c{i}", name="profile_dataset", arguments={})])
            for i in range(5)
        ]
    )
    agent = AnalystAgent(llm=looping)
    result = agent.analyze(DATA, "loop forever", max_turns=3)

    # 3 budgeted tool-calling turns + 1 tool-free final-answer attempt
    assert len(looping.calls) == 4
    assert "max turns" in result.answer
    assert len(result.steps) == 3  # no tools ran after the budget ran out


def test_agent_answers_from_evidence_when_budget_exhausted():
    """Budget exhaustion must still produce a grounded final answer."""
    script = [
        ChatResponse(
            tool_calls=[ToolCall(id="c1", name="profile_dataset", arguments={})]
        ),
        ChatResponse(text="The dataset has 20 rows with no missing values."),
    ]
    agent = AnalystAgent(llm=FakeLLM(script))
    result = agent.analyze(DATA, "how many rows?", max_turns=1)

    assert result.answer == "The dataset has 20 rows with no missing values."
    assert len(result.steps) == 1  # the forced call never ran a tool
    assert result.validation["passed"] is True  # 20 is grounded in the profile


def test_agent_seeds_history_and_grounds_against_it():
    """A follow-up replays earlier turns and may reuse their tool numbers."""
    fake = FakeLLM([ChatResponse(text="The mean revenue was 1183.72.")])
    agent = AnalystAgent(llm=fake)
    result = agent.analyze(
        DATA,
        "what was the mean again?",
        max_turns=4,
        history=[
            {
                "question": "total revenue?",
                "answer": "Total revenue was 23674.45.",
                "tool_results": ["mean revenue 1183.7225"],
            }
        ],
    )

    sent = fake.calls[0]["messages"]
    assert any("total revenue?" in (m.get("content") or "") for m in sent)
    assert any(
        m["role"] == "assistant" and "23674.45" in (m.get("content") or "")
        for m in sent
    )
    assert any("Follow-up question" in (m.get("content") or "") for m in sent)

    # no tools ran this turn, yet the reused number is grounded via prior evidence
    assert result.steps == []
    assert result.validation["passed"] is True


def test_agent_without_llm_key_returns_placeholder():
    agent = AnalystAgent(llm=LLMService(api_key=""))  # LLMService() with no key configured
    result = agent.analyze(DATA, "q")
    assert "not configured" in result.answer


def test_chart_paths_from_create_chart_steps():
    from app.agents.analyst import _chart_paths

    steps = [
        {"tool": "profile_dataset", "status": "ok", "result": "20 rows"},
        {"tool": "create_chart", "status": "ok", "result": "/tmp/charts/a.png"},
        {"tool": "create_chart", "status": "error", "result": "bad spec"},
        {"tool": "create_chart", "status": "ok", "result": "not-a-png"},
    ]
    assert _chart_paths(steps) == ["/tmp/charts/a.png"]
    assert _chart_paths(None) == []
    assert _chart_paths([]) == []
