"""Pydantic schemas describing analysis outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    dataset: str
    question: str
    profile: dict = Field(default_factory=dict)
    statistics: dict = Field(default_factory=dict)
    answer: str = ""
    chart_paths: list[str] = Field(default_factory=list)
    steps: list[dict] = Field(
        default_factory=list,
        description="Tool-calling log: {tool, arguments, status, result} per call.",
    )
    validation: dict = Field(
        default_factory=dict,
        description="Grounding verdict: {passed, checked, unsupported, tool_results}.",
    )
