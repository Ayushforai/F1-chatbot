"""FastAPI wrapper around the Racecoe chat pipeline, plus the web UI."""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import initialize_pipeline, process_query
from utils.llm import active_model_label, describe_config, get_model_name
from utils.season_calendar import get_season_calendar, list_calendar_years

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"

_ready = False
_ready_error: str | None = None
_sessions: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _cors_origins() -> list[str]:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if not raw or raw == "*":
        # Local/dev default. Set CORS_ORIGINS to a comma-separated allowlist in production.
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class ChatRequest(BaseModel):
    message: str = ""
    session_id: str | None = None


class ResetRequest(BaseModel):
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str = ""
    body: str = ""
    citation: str | None = None
    category: str = ""
    awaiting_year: bool = False
    awaiting_venue: bool = False
    session_id: str


def _boot() -> None:
    global _ready, _ready_error
    try:
        initialize_pipeline()
        _ready = True
        print(f" [API] Racecoe ready [{active_model_label()}].")
    except Exception as exc:
        _ready_error = str(exc)
        print(f" [API] Startup failed: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("F1_SKIP_WARMUP") != "1":
        threading.Thread(target=_boot, daemon=True).start()
    yield


app = FastAPI(
    title="Racecoe",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_query(session_id: str, message: str) -> dict | None:
    with _lock:
        history = _sessions.setdefault(session_id, [])
        return process_query(history, message)


def _chat_payload(result: dict | None, session_id: str) -> dict:
    payload = result or {
        "answer": "",
        "body": "",
        "citation": None,
        "category": "",
        "awaiting_year": False,
        "awaiting_venue": False,
    }
    payload["session_id"] = session_id
    return payload


async def _handle_chat(payload: ChatRequest) -> JSONResponse | dict:
    if not _ready:
        return JSONResponse(
            {"error": _ready_error or "Pit wall is still warming up."},
            status_code=503,
        )

    message = (payload.message or "").strip()
    if not message:
        return JSONResponse({"error": "Empty query."}, status_code=400)

    session_id = (payload.session_id or "").strip() or str(uuid.uuid4())
    result = await asyncio.to_thread(_run_query, session_id, message)
    return _chat_payload(result, session_id)


@app.post("/chat")
async def chat(payload: ChatRequest):
    """Wrap `process_query` for one user turn."""
    return await _handle_chat(payload)


@app.post("/api/chat")
async def api_chat(payload: ChatRequest):
    return await _handle_chat(payload)


@app.get("/health")
@app.get("/api/health")
def health():
    cfg = describe_config()
    return {
        "ready": _ready,
        "error": _ready_error,
        "model": get_model_name(),
        "provider": cfg["provider"],
        "model_label": cfg["label"],
        "has_api_key": cfg["has_api_key"],
    }


@app.get("/api/calendar")
def calendar(year: int | None = Query(default=None)):
    years = list_calendar_years()
    if year is None:
        year = years[0] if years else 2026
    payload = get_season_calendar(year)
    payload["years"] = years
    return payload


@app.post("/api/reset")
def reset(payload: ResetRequest | None = None):
    session_id = ((payload.session_id if payload else None) or "").strip()
    with _lock:
        if session_id:
            _sessions.pop(session_id, None)
        else:
            _sessions.clear()
    return {"ok": True, "session_id": session_id or str(uuid.uuid4())}


def _spa_response(path: str) -> FileResponse | JSONResponse:
    if DIST.is_dir():
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        index = DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
    return JSONResponse(
        {
            "error": (
                "Frontend build not found. Run `npm install && npm run build` "
                "in frontend/, or use `npm run dev` during development."
            )
        },
        status_code=404,
    )


@app.get("/")
def spa_index():
    return _spa_response("")


@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api/") or path in {"chat", "health", "docs", "redoc", "openapi.json"}:
        return JSONResponse({"error": "Not found."}, status_code=404)
    return _spa_response(path)


# TestClient and health checks import MODEL_NAME from server
MODEL_NAME = get_model_name()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")
