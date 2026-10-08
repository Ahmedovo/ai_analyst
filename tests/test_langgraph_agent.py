"""Verify the agent is a LangGraph StateGraph with the expected topology."""

from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from app.agents.analyst import AnalystAgent, AnalystState, build_system_prompt
from app.services.llm import ChatResponse, ToolCall

DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.script.pop(0)


def test_graph_is_compiled_langgraph():
    agent = AnalystAgent(llm=FakeLLM([ChatResponse(text="done")]))
    assert isinstance(agent.graph, CompiledStateGraph)


def test_graph_topology():
    agent = AnalystAgent(llm=FakeLLM([ChatResponse(text="done")]))
    graph = agent.graph.get_graph()
    nodes = set(graph.nodes)
    assert {"agent", "tools"} <= nodes

    edges = {(e.source, e.target) for e in graph.edges}
    assert ("__start__", "agent") in edges          # START -> agent
    assert ("tools", "agent") in edges              # cycle back
    # agent -> END (conditional) and agent -> tools both exist
    assert ("agent", "__end__") in edges or any(
        e.conditional for e in graph.edges if e.source == "agent"
    )
    assert ("agent", "tools") in edges or any(
        e.conditional for e in graph.edges if e.source == "agent"
    )


def test_state_schema():
    hints = AnalystState.__annotations__
    for key in ("dataset", "question", "max_turns", "turns", "messages",
                "steps", "answer", "done"):
        assert key in hints


def test_run_produces_final_state_fields():
    fake = FakeLLM(
        [
            ChatResponse(tool_calls=[ToolCall(id="c1", name="profile_dataset", arguments={})]),
            ChatResponse(text="All good."),
        ]
    )
    agent = AnalystAgent(llm=fake)
    result = agent.analyze(DATA, "q")
    assert result.answer == "All good."
    assert result.steps[0]["tool"] == "profile_dataset"
    assert result.validation["passed"] is True
    assert build_system_prompt().splitlines()[0] == "You are an autonomous data analyst."


def test_grounding_node_rejects_then_accepts():
    """A hallucinated number triggers the validate node -> retry -> fixed answer."""
    fake = FakeLLM(
        [
            ChatResponse(
                text="Computing the total.",
                tool_calls=[
                    ToolCall(id="c1", name="execute_sql",
                             arguments={"sql": "SELECT SUM(revenue) AS total FROM {table}"})
                ],
            ),
            ChatResponse(text="Total revenue was 23674.45, up 4242% over the plan."),
            ChatResponse(text="Total revenue was 23674.45."),
        ]
    )
    agent = AnalystAgent(llm=fake)
    result = agent.analyze(DATA, "What was total revenue?")

    # first answer failed grounding, second passed
    assert result.validation["passed"] is True
    assert result.answer == "Total revenue was 23674.45."
    assert len(fake.calls) == 3

    # the retry turn received the validation feedback as a user message
    retry_messages = fake.calls[2]["messages"]
    feedback = [m for m in retry_messages if m["role"] == "user"][-1]
    assert "grounding validation" in feedback["content"]
    assert "4242" in feedback["content"]

    # the failed verdict is preserved for inspection... final state wins
    assert result.steps[0]["tool"] == "execute_sql"


def test_grounding_node_gives_up_after_max_retries():
    fake = FakeLLM(
        [
            ChatResponse(tool_calls=[ToolCall(id="c1", name="profile_dataset", arguments={})]),
            ChatResponse(text="There are 9999 units."),      # unsupported
            ChatResponse(text="Still claiming 9999 units."),  # unsupported again -> stop
        ]
    )
    agent = AnalystAgent(llm=fake)
    result = agent.analyze(DATA, "how many units?")

    assert len(fake.calls) == 3  # no third retry
    assert result.validation["passed"] is False
    assert "9999" in result.validation["unsupported"]
