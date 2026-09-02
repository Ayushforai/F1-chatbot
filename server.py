"""FastAPI wrapper around the existing F1 chat pipeline, plus the Pit Wall UI."""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import MODEL_NAME, initialize_pipeline, process_query
from utils.season_calendar import get_season_calendar, list_calendar_years

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"

_ready = False
_ready_error: str | None = None
_sessions: dict[str, list[dict]] = {}
_lock = threading.Lock()


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
        print(" [API] Pit wall ready for radio.")
    except Exception as exc:
        _ready_error = str(exc)
        print(f" [API] Startup failed: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("F1_SKIP_WARMUP") != "1":
        threading.Thread(target=_boot, daemon=True).start()
    yield


app = FastAPI(
    title="F1 Pit Wall",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    return {
        "ready": _ready,
        "error": _ready_error,
        "model": MODEL_NAME,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5001, log_level="info")
