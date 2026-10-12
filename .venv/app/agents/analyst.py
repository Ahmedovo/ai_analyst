"""Autonomous analyst agent built on LangGraph.

Graph topology (ReAct-style cycle plus a grounding gate on the answer):

    START ─► agent ──(tool calls)──► tools ──► agent
                 │
                 └──(final answer)──► validate ──(grounded?)──► END
                                         │
                                         └──(unsupported numbers, max 1 retry)──► agent

State flows through a typed ``AnalystState``; the model layer stays the
provider-agnostic ``LLMService`` (raw HTTP, any provider).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.grounding import validate_answer
from app.schemas.analysis import AnalysisResult
from app.services.llm import LLMService
from app.tools.registry import TOOL_DEFINITIONS, run_tool

#: how many times a failed grounding check sends the answer back for repair
MAX_ANSWER_RETRIES = 1

#: shown only when even the tool-free final-answer attempt fails
STOPPED_PLACEHOLDER = "Stopped before reaching a final answer (max turns reached)."

#: appended when the turn budget runs out — forces a tool-free final answer
BUDGET_NUDGE = (
    "You are out of tool-call budget. Using ONLY the tool results already in "
    "this conversation, write your final answer now. Do not request more tools."
)


def _chart_paths(steps: list[dict] | None) -> list[str]:
    """PNG paths saved by successful ``create_chart`` steps."""
    paths: list[str] = []
    for step in steps or []:
        if step.get("tool") == "create_chart" and step.get("status") == "ok":
            result = str(step.get("result", "")).strip()
            if result.lower().endswith(".png"):
                paths.append(result)
    return paths


def _evidence_digest(state: dict[str, Any], reason: str | None = None) -> str:
    """Deterministic markdown summary of the tool results gathered so far.

    Last-resort answer when the model cannot be reached (provider outage,
    rate limit, timeout). Evidence-only: every number comes straight out of a
    tool result, and no args/ordinals are included that could trip the number
    validator. The fallback is shown as-is (not grounding-scored).
    """
    steps = state.get("steps") or []
    lines = [
        "**Analysis interrupted** — the model could not be reached to finish "
        "the answer."
    ]
    if reason:
        reason = " ".join(str(reason).split())
        if len(reason) > 200:
            reason = reason[:200] + "…"
        lines.append(f"Reason: `{reason}`")
    if not steps:
        lines.append("_No tool results were collected before the interruption._")
    else:
        lines.append("Tool results collected before the interruption:")
        for step in steps:
            tool = step.get("tool", "?")
            status = step.get("status", "?")
            result = str(step.get("result", "")).strip()
            if len(result) > 400:
                result = result[:400] + " …"
            lines.append(f"- **{tool}** ({status}) — {result}")
    return "\n\n".join(lines)


def build_system_prompt(max_turns: int = 8) -> str:
    """System prompt describing the role, the tools, and the working rules."""
    tool_lines = "\n".join(
        f"- {t['name']}: {t['description']}" for t in TOOL_DEFINITIONS
    )
    return f"""You are an autonomous data analyst.

You have access to these tools:

{tool_lines}

Your job is to answer the user's analytical question.

Rules:
- The conversation may contain earlier questions and answers. Treat the latest
  question as a follow-up: build on those results instead of starting over, and
  reuse earlier tool evidence when it already answers the question.
- Plan before you act: think step by step about which tools you need and in what order.
- Batch independent calls: you can request several tool calls in a single
  response (for example every detect_anomalies column at once, or statistics
  plus group_by). Only calls that depend on earlier results need their own turn.
- You have at most {max_turns} tool-calling turns — budget them. Spend them on
  what the user actually asked: if they ask for charts, call create_chart
  before finishing, and always leave room to write the final answer.
- Never invent numerical results. Use tools to obtain data.
- Base every number in your final answer on a tool result you actually received.
- Start with profile_dataset to understand the columns, types, and quality of the data.
- Use validate_data to check data quality (nulls, ranges, cross-column consistency)
  before drawing conclusions, and report any failed rules as caveats.
- Use execute_sql or group_by to break the problem down (trends over time, per
  category, before/after comparisons), calculate_statistics for distributions,
  detect_anomalies for outliers, and create_chart when a visual helps.
- If a tool returns an ERROR, read the message, correct your arguments, and retry.
- Keep going until you have enough evidence, then give a concise final answer:
  state the conclusion first, support it with the exact numbers from tool
  results, and mention any caveats about data quality.
- Your answer will be validated automatically: every number it contains must
  appear in a tool result. Reply in the same language as the user's question.
"""


class AnalystState(TypedDict):
    """Shared state for every graph node."""

    dataset: str
    question: str
    max_turns: int
    turns: int  # model calls made so far
    messages: list[dict[str, Any]]  # neutral chat format
    steps: list[dict[str, Any]]  # tool-call audit log (full results)
    prior_evidence: list[str]  # tool results from earlier conversation turns
    answer: str
    done: bool
    validation: dict[str, Any]  # grounding verdict of the last check
    validation_retries: int


class AnalystAgent:
    """LangGraph agent: plan -> call tools -> observe -> repeat -> answer -> validate."""

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or LLMService()
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(AnalystState)
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)
        graph.add_node("validate", self._validate_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent",
            self._route,
            {"tools": "tools", "validate": "validate"},
        )
        graph.add_edge("tools", "agent")
        graph.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {"agent": "agent", "end": END},
        )
        return graph.compile()

    def _route(self, state: AnalystState) -> str:
        """While the model is still calling tools, run them; on a final
        answer, send it through the grounding gate."""
        return "tools" if not state["done"] else "validate"

    def _route_after_validate(self, state: AnalystState) -> str:
        return "end" if state["done"] else "agent"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _agent_node(self, state: AnalystState) -> dict[str, Any]:
        """One model turn: produce a final answer or a set of tool calls."""
        if state["turns"] >= state["max_turns"]:
            return self._forced_final_answer(state)

        response = self.llm.chat(state["messages"], tools=TOOL_DEFINITIONS)
        turns = state["turns"] + 1

        if not response.has_tool_calls:
            return {"done": True, "answer": response.text, "turns": turns}

        # Record the assistant turn — its text is the model's plan/reasoning.
        assistant_msg = {
            "role": "assistant",
            "content": response.text or None,
            "tool_calls": [
                {"id": c.id, "name": c.name, "arguments": c.arguments}
                for c in response.tool_calls
            ],
        }
        return {"messages": state["messages"] + [assistant_msg], "turns": turns}

    def _forced_final_answer(self, state: AnalystState) -> dict[str, Any]:
        """Turn budget exhausted: give the model ONE tool-free chance to write
        a final answer from the evidence already gathered, instead of failing
        the run with a placeholder message."""
        if not state["steps"] or state["answer"]:
            # nothing to summarise, or an answer already exists
            return {"done": True, "answer": state["answer"] or STOPPED_PLACEHOLDER}
        try:
            response = self.llm.chat(
                state["messages"] + [{"role": "user", "content": BUDGET_NUDGE}],
                tools=None,  # no tools offered — this call must be the answer
            )
        except Exception:  # noqa: BLE001 — never fail the run on the last call
            return {"done": True, "answer": STOPPED_PLACEHOLDER}
        if response.has_tool_calls or not (response.text or "").strip():
            return {"done": True, "answer": STOPPED_PLACEHOLDER}
        return {"done": True, "answer": response.text, "turns": state["turns"] + 1}

    def _tools_node(self, state: AnalystState) -> dict[str, Any]:
        """Execute the pending tool calls and append results to the state."""
        messages = list(state["messages"])
        steps = list(state["steps"])
        pending = messages[-1].get("tool_calls") or []

        for call in pending:
            try:
                content = run_tool(call["name"], call["arguments"], state["dataset"])
                status = "ok"
            except Exception as exc:  # noqa: BLE001 - errors go back to the model
                content = f"ERROR: {exc}"
                status = "error"
            steps.append(
                {
                    "tool": call["name"],
                    "arguments": call["arguments"],
                    "status": status,
                    "result": content[:20000],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": content,
                }
            )

        return {"messages": messages, "steps": steps}

    def _validate_node(self, state: AnalystState) -> dict[str, Any]:
        """Grounding gate: every number in the answer must trace back to a
        tool result. On failure, send the answer back once with feedback."""
        verdict = validate_answer(
            state["answer"],
            state["steps"],
            state["question"],
            prior_results=state.get("prior_evidence", []),
        )
        retries = state["validation_retries"]

        if verdict["passed"] or retries >= MAX_ANSWER_RETRIES:
            return {"validation": verdict, "done": True}

        feedback = (
            "Your previous answer failed grounding validation. These numbers were "
            "not found in any tool result: "
            + ", ".join(verdict["unsupported"])
            + ". Either call another tool to obtain them, or remove/correct the "
            "unsupported figures, then give the answer again."
        )
        return {
            "validation": verdict,
            "messages": state["messages"] + [{"role": "user", "content": feedback}],
            "answer": "",
            "done": False,
            "validation_retries": retries + 1,
        }

    # ------------------------------------------------------------------
    # Public API (unchanged)
    # ------------------------------------------------------------------

    def analyze(
        self,
        dataset: str | Path,
        question: str,
        max_turns: int = 8,
        history: list[dict[str, Any]] | None = None,
    ) -> AnalysisResult:
        """Run the graph and return the answer, tool log, and validation verdict.

        ``history`` replays earlier ``{question, answer, tool_results}`` turns so
        the run behaves as a follow-up rather than a fresh question.
        """
        final = self._run_graph(dataset, question, max_turns, history)
        path = Path(dataset)
        return AnalysisResult(
            dataset=str(path),
            question=question,
            answer=final["answer"],
            steps=final["steps"],
            validation=final["validation"],
            chart_paths=_chart_paths(final["steps"]),
        )

    def stream(
        self,
        dataset: str | Path,
        question: str,
        max_turns: int = 8,
        history: list[dict[str, Any]] | None = None,
    ):
        """Run the graph as an iterator of JSON-safe event dicts.

        Event types::

            {"type": "node",       "node": "agent"|"tools"|"validate"}
            {"type": "plan",       "text": str}          # assistant reasoning
            {"type": "step",       "step": {...}}        # one tool executed
            {"type": "validation", "validation": {...}}  # grounding verdict
            {"type": "retry",      "unsupported": [...]} # answer sent back
            {"type": "done",       "result": AnalysisResult-dict}
        """
        path = Path(dataset)
        state = dict(self._initial_state(dataset, question, max_turns, history))
        seen_steps = 0

        try:
            for update in self.graph.stream(
                state, config={"recursion_limit": max_turns * 3 + 10}
            ):
                for node, partial in update.items():
                    yield {"type": "node", "node": node}
                    state.update(partial)

                    if node == "agent":
                        messages = partial.get("messages") or []
                        if messages:
                            text = messages[-1].get("content")
                            if text:
                                yield {"type": "plan", "text": text}
                    elif node == "tools":
                        steps = partial.get("steps") or []
                        for step in steps[seen_steps:]:
                            yield {"type": "step", "step": step}
                        seen_steps = max(seen_steps, len(steps))
                    elif node == "validate":
                        verdict = partial.get("validation")
                        if verdict:
                            yield {"type": "validation", "validation": verdict}
                            if not partial.get("done", True):
                                yield {
                                    "type": "retry",
                                    "unsupported": verdict.get("unsupported", []),
                                }
        except Exception as exc:  # noqa: BLE001 — never end a stream without an answer
            state = self._crashed_state(state, exc)

        yield {
            "type": "done",
            "result": AnalysisResult(
                dataset=str(path),
                question=question,
                answer=state.get("answer", ""),
                steps=state.get("steps", []),
                validation=state.get("validation", {}),
                chart_paths=_chart_paths(state.get("steps", [])),
            ).model_dump(),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _initial_state(
        self,
        dataset: str | Path,
        question: str,
        max_turns: int,
        history: list[dict[str, Any]] | None = None,
    ) -> AnalystState:
        path = Path(dataset)
        history = history or []

        # Replay earlier turns so the model continues the conversation.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(max_turns)}
        ]
        for turn in history:
            messages.append(
                {
                    "role": "user",
                    "content": f"Dataset: {path}\n\nQuestion: {turn.get('question', '')}",
                }
            )
            messages.append({"role": "assistant", "content": turn.get("answer", "")})
        label = "Follow-up question" if history else "Question"
        messages.append(
            {"role": "user", "content": f"Dataset: {path}\n\n{label}: {question}"}
        )

        # Numbers reused from earlier answers stay grounded against earlier tools.
        prior_evidence = [
            str(result)
            for turn in history
            for result in (turn.get("tool_results") or [])
        ]

        return {
            "dataset": str(path),
            "question": question,
            "max_turns": max_turns,
            "turns": 0,
            "messages": messages,
            "steps": [],
            "prior_evidence": prior_evidence,
            "answer": "",
            "done": False,
            "validation": {},
            "validation_retries": 0,
        }

    def _run_graph(
        self,
        dataset: str | Path,
        question: str,
        max_turns: int,
        history: list[dict[str, Any]] | None = None,
    ) -> AnalystState:
        state = dict(self._initial_state(dataset, question, max_turns, history))
        try:
            # Stream and fold partials into `state` so that if the run crashes
            # mid-way, the partial evidence gathered so far is still available
            # for the fallback digest (invoke() discards it on exception).
            for update in self.graph.stream(
                state, config={"recursion_limit": max_turns * 3 + 10}
            ):
                for partial in update.values():
                    state.update(partial)
        except Exception as exc:  # noqa: BLE001 — never lose a run to a provider hiccup
            return self._crashed_state(state, exc)
        return state

    def _crashed_state(self, state: AnalystState, exc: Exception) -> AnalystState:
        """Turn a mid-run crash into a deliverable result: an evidence digest
        instead of nothing. The answer is built from tool results already
        gathered and shown as-is (not grounding-scored — retries would
        re-enter the loop, and the reason text's digits would trip the
        validator), and the run is marked done."""
        state["answer"] = _evidence_digest(state, reason=str(exc))
        state["done"] = True
        state["validation"] = {
            "passed": False,
            "checked": 0,
            "tool_results": 0,
            "unsupported": [],
            "note": f"Run interrupted ({type(exc).__name__}) — evidence shown as-is.",
        }
        return state
