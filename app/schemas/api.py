"""API request/response schemas (separate from domain models)."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
