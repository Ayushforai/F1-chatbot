"""Concurrent access checks for the HTTP chat API."""

import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ["F1_SKIP_WARMUP"] = "1"

from fastapi.testclient import TestClient

import server


class TestConcurrentSessions(unittest.TestCase):
    def setUp(self):
        server._ready = True
        server._ready_error = None
        server._sessions.clear()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server._sessions.clear()

    def test_different_sessions_do_not_share_history(self):
        def record(history, message):
            history.append({"query": message, "answer": f"ans-{message}"})
            return {
                "answer": f"ans-{message}",
                "body": f"ans-{message}",
                "citation": None,
                "category": "historical",
                "awaiting_year": False,
                "awaiting_venue": False,
            }

        with patch.object(server, "process_query", side_effect=record):
            r1 = self.client.post(
                "/api/chat",
                json={"message": "user-a", "session_id": "session-a"},
            )
            r2 = self.client.post(
                "/api/chat",
                json={"message": "user-b", "session_id": "session-b"},
            )

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(server._sessions["session-a"]), 1)
        self.assertEqual(len(server._sessions["session-b"]), 1)
        self.assertEqual(server._sessions["session-a"][0]["query"], "user-a")
        self.assertEqual(server._sessions["session-b"][0]["query"], "user-b")

    def test_global_lock_serializes_all_chat_requests(self):
        """Document current behavior: one global lock queues every session."""
        order: list[tuple[str, str]] = []
        active = {"count": 0, "peak": 0}
        track = threading.Lock()

        def slow_process(history, message):
            with track:
                active["count"] += 1
                active["peak"] = max(active["peak"], active["count"])
                order.append(("start", message))
            time.sleep(0.12)
            with track:
                active["count"] -= 1
                order.append(("end", message))
            history.append({"query": message})
            return {
                "answer": message,
                "body": message,
                "citation": None,
                "category": "historical",
                "awaiting_year": False,
                "awaiting_venue": False,
            }

        with patch.object(server, "process_query", side_effect=slow_process):
            threads = []
            for idx in range(3):
                thread = threading.Thread(
                    target=lambda i=idx: self.client.post(
                        "/api/chat",
                        json={"message": f"m{i}", "session_id": f"s{i}"},
                    )
                )
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()

        # If requests ran in parallel, peak would be > 1.
        self.assertEqual(active["peak"], 1)
        starts = [item for item in order if item[0] == "start"]
        ends = [item for item in order if item[0] == "end"]
        self.assertEqual(len(starts), 3)
        self.assertEqual(len(ends), 3)
        # Fully serialized: each request finishes before the next starts.
        self.assertEqual(order[0][0], "start")
        self.assertEqual(order[1][0], "end")


if __name__ == "__main__":
    unittest.main()
