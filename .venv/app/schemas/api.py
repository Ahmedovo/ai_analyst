"""API request/response schemas (separate from domain models)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HistoryTurn(BaseModel):
    """One earlier exchange, replayed so follow-up questions have context."""

    question: str = Field(..., min_length=1, description="The earlier question")
    answer: str = Field(default="", description="The earlier (final) answer")
    tool_results: list[str] = Field(
        default_factory=list,
        description=(
            "Tool-result texts from that turn. Reused numbers in a follow-up "
            "answer stay grounded against this earlier evidence."
        ),
    )


class AnalyzeRequest(BaseModel):
    dataset: str = Field(
        ..., min_length=1, description="CSV file name inside data/", examples=["sales.csv"]
    )
    question: str = Field(
        ...,
        min_length=3,
        description="Natural-language analytical question",
        examples=["Why did revenue decrease in Q3?"],
    )
    max_turns: int = Field(
        default=8, ge=1, le=20, description="Max model turns before forced stop"
    )
    history: list[HistoryTurn] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Earlier Q&A turns (oldest first). When present the agent runs as a "
            "follow-up: prior exchanges are replayed to the model and their tool "
            "results join the grounding check."
        ),
    )


class HealthInfo(BaseModel):
    status: str
    provider: str
    model: str
    llm_available: bool = Field(
        description="True when an API key is configured (key itself is never exposed)"
    )


class DatasetInfo(BaseModel):
    name: str
    size: int


class UploadResponse(BaseModel):
    name: str
    size: int


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict
