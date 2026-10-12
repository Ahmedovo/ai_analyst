"""FastAPI backend wrapping the LangGraph analyst agent.

Run with:  uvicorn app.api.main:app --reload   (or: python -m app.api)
Docs:      http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.agents.analyst import AnalystAgent
from app.schemas.analysis import AnalysisResult
from app.schemas.api import AnalyzeRequest, DatasetInfo, HealthInfo, ToolInfo, UploadResponse
from app.tools.registry import TOOL_DEFINITIONS

BASE_DIR = Path(__file__).resolve().parents[2]  # project root
DATA_DIR = BASE_DIR / "data"
CHARTS_DIR = BASE_DIR / "generated" / "charts"


def _safe_child(directory: Path, name: str, suffix: str) -> Path:
    """Resolve ``name`` inside ``directory``; reject traversal and wrong types."""
    if not name or Path(name).name != name or not name.lower().endswith(suffix):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid name: expected a bare '{suffix}' file name",
        )
    target = directory / name
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"'{name}' not found")
    return target


def _json_default(obj):
    """Serialise numpy/pandas scalars in streamed events."""
    return obj.item() if hasattr(obj, "item") else str(obj)


def create_app(agent: AnalystAgent | None = None) -> FastAPI:
    """App factory — inject an agent (e.g. with a fake LLM) for tests."""
    application = FastAPI(
        title="AI Data Analyst API",
        description=(
            "Ask questions about CSV datasets. A LangGraph agent plans, calls "
            "tools (profiling, SQL, statistics, charts, validation), and returns "
            "answers with every number grounded in tool output."
        ),
        version="1.0.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.agent = agent or AnalystAgent()

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @application.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "title": "AI Data Analyst API",
            "docs": "/docs",
            "endpoints": [
                "GET  /api/health",
                "GET  /api/tools",
                "GET  /api/datasets",
                "POST /api/datasets          (upload a CSV)",
                "POST /api/analyze           (ask a question)",
                "POST /api/analyze/stream    (same, streamed as NDJSON events)",
                "GET  /api/charts",
                "GET  /api/charts/{name}",
            ],
        }

    @application.get("/api/health", response_model=HealthInfo, tags=["meta"])
    async def health() -> HealthInfo:
        llm = application.state.agent.llm
        config = getattr(llm, "config", None)  # injected test doubles may differ
        return HealthInfo(
            status="ok",
            provider=getattr(config, "provider", "unknown"),
            model=getattr(config, "model", "unknown"),
            llm_available=bool(getattr(llm, "available", False)),
        )

    @application.get("/api/tools", tags=["meta"])
    async def tools() -> dict:
        infos = [ToolInfo(**t) for t in TOOL_DEFINITIONS]
        return {"count": len(infos), "tools": infos}

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------

    @application.get("/api/datasets", response_model=list[DatasetInfo], tags=["datasets"])
    async def datasets() -> list[DatasetInfo]:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return [
            DatasetInfo(name=p.name, size=p.stat().st_size)
            for p in sorted(DATA_DIR.glob("*.csv"))
        ]

    @application.post("/api/datasets", response_model=UploadResponse, tags=["datasets"])
    async def upload_dataset(file: UploadFile = File(...)) -> UploadResponse:
        filename = file.filename or ""
        if not filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only .csv files are supported")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        name = Path(filename).name  # strip any client-side path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / name).write_bytes(content)
        return UploadResponse(name=name, size=len(content))

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    @application.post("/api/analyze", response_model=AnalysisResult, tags=["analysis"])
    async def analyze(payload: AnalyzeRequest) -> AnalysisResult:
        dataset = _safe_child(DATA_DIR, payload.dataset, ".csv")
        agent: AnalystAgent = application.state.agent
        history = [turn.model_dump() for turn in payload.history]
        # The agent is blocking (sync LLM + pandas calls) — keep the loop free.
        try:
            result = await asyncio.to_thread(
                agent.analyze,
                dataset,
                payload.question,
                payload.max_turns,
                history=history,
            )
        except Exception as exc:  # noqa: BLE001 — surface LLM/tool failures cleanly
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result.model_copy(update={"dataset": payload.dataset})

    @application.post("/api/analyze/stream", tags=["analysis"])
    async def analyze_stream(payload: AnalyzeRequest) -> StreamingResponse:
        """Newline-delimited JSON events as the agent loop executes.

        One event per line: ``node``, ``plan``, ``step``, ``validation``,
        ``retry``, ``done`` (see ``AnalystAgent.stream``). If the loop dies
        mid-run, a final ``{"type": "error", "message": ...}`` line is emitted
        instead of closing the connection abruptly.
        """
        dataset = _safe_child(DATA_DIR, payload.dataset, ".csv")
        agent: AnalystAgent = application.state.agent
        history = [turn.model_dump() for turn in payload.history]

        def generate():
            try:
                for event in agent.stream(
                    dataset,
                    payload.question,
                    payload.max_turns,
                    history=history,
                ):
                    if event["type"] == "done":
                        # echo the requested name, never a filesystem path
                        event["result"]["dataset"] = payload.dataset
                    yield json.dumps(event, default=_json_default) + "\n"
            except Exception as exc:  # noqa: BLE001 — never kill the connection silently
                yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------

    @application.get("/api/charts", tags=["charts"])
    async def list_charts() -> dict:
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        return {"charts": sorted(p.name for p in CHARTS_DIR.glob("*.png"))}

    @application.get("/api/charts/{name}", tags=["charts"])
    async def get_chart(name: str) -> FileResponse:
        path = _safe_child(CHARTS_DIR, name, ".png")
        return FileResponse(path, media_type="image/png")

    return application


app = create_app()
