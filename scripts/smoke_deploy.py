#!/usr/bin/env python3
"""Smoke-check Racecoe API health + Monaco 2021 follow-up stickiness.

Usage:
  F1_SKIP_WARMUP=1 PYTHONPATH=. python scripts/smoke_deploy.py
  BASE_URL=http://127.0.0.1:5001 python scripts/smoke_deploy.py --http
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("F1_SKIP_WARMUP", "1")


MONACO_ANSWER = (
    "The results for the 2021 Monaco Grand Prix are as follows:\n\n"
    "Classified finishers (18):\n"
    "1. Max Verstappen (Red Bull) - 1:38:56.820, 25.0 pts\n"
    "2. Carlos Sainz (Ferrari) - +8.968, 18.0 pts\n"
    "3. Lando Norris (McLaren) - +19.427, 15.0 pts, fastest lap 1:14.670 on lap 76\n"
)


def smoke_inprocess() -> None:
    from utils.session_results import session_results_offer
    import app
    from fastapi.testclient import TestClient
    import server

    history = [
        {
            "query": "Results of Monaco GP 2021",
            "category": "historical",
            "answer": MONACO_ANSWER + session_results_offer(),
            "year": 2021,
            "country": "Monaco",
            "race_lookup_query": "Results of Monaco GP 2021",
            "awaiting_session_choice": True,
            "pending_query": "Results of Monaco GP 2021",
        }
    ]
    payload = app.process_query(history, "who was third?")
    assert payload is not None, "process_query returned None"
    assert "Lando Norris" in payload["body"], payload["body"]
    assert "Which session would you like" not in payload["body"], payload["body"]
    print("OK in-process follow-up: Lando Norris (Monaco 2021)")

    server._ready = True
    server._ready_error = None
    client = TestClient(server.app)
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    body = health.json()
    assert "model" in body and "provider" in body, body
    print(f"OK health: provider={body.get('provider')} model={body.get('model')}")


def smoke_http(base_url: str) -> None:
    import requests

    health = requests.get(f"{base_url.rstrip('/')}/api/health", timeout=30)
    health.raise_for_status()
    body = health.json()
    print(f"OK http health: {body}")
    if not body.get("ready"):
        print("WARN: API not ready yet (warmup). Follow-up chat smoke skipped.")
        return

    chat = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={"message": "Results of Monaco GP 2021", "session_id": "smoke-deploy"},
        timeout=180,
    )
    chat.raise_for_status()
    first = chat.json()
    print("OK monaco results:", (first.get("body") or "")[:120], "...")

    follow = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={"message": "who was third?", "session_id": first["session_id"]},
        timeout=180,
    )
    follow.raise_for_status()
    second = follow.json()
    body_text = second.get("body") or ""
    assert "Lando Norris" in body_text or "Norris" in body_text, body_text
    assert "Which session would you like" not in body_text, body_text
    print("OK http follow-up sticks to Monaco session")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="Hit a running server")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:5001"))
    args = parser.parse_args()
    if args.http:
        smoke_http(args.base_url)
    else:
        smoke_inprocess()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
