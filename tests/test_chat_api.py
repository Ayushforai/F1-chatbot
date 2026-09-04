import os
import unittest
from unittest.mock import patch

os.environ["F1_SKIP_WARMUP"] = "1"

from fastapi.testclient import TestClient

import server


class TestFastAPIChatWrapper(unittest.TestCase):
    def setUp(self):
        os.environ["F1_SKIP_WARMUP"] = "1"
        server._ready = True
        server._ready_error = None
        server._sessions.clear()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server._sessions.clear()
        server._ready = True
        server._ready_error = None

    def test_chat_empty_message_is_400(self):
        response = self.client.post("/chat", json={"message": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Empty query.")

    def test_chat_not_ready_is_503(self):
        server._ready = False
        server._ready_error = None
        response = self.client.post("/chat", json={"message": "who won monaco 2021?"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("warming up", response.json()["error"])

    def test_chat_wraps_process_query(self):
        fake = {
            "answer": "Charles Leclerc won.",
            "body": "Charles Leclerc won.",
            "citation": "Historical CSV — 2021",
            "category": "historical",
            "awaiting_year": False,
            "awaiting_venue": False,
        }
        with patch.object(server, "process_query", return_value=fake) as mocked:
            response = self.client.post(
                "/chat",
                json={"message": "who won monaco 2021?", "session_id": "sess-1"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["body"], "Charles Leclerc won.")
        self.assertEqual(payload["session_id"], "sess-1")
        mocked.assert_called_once()
        history, query = mocked.call_args.args
        self.assertEqual(query, "who won monaco 2021?")
        self.assertIs(history, server._sessions["sess-1"])

    def test_api_chat_alias_uses_same_wrapper(self):
        fake = {
            "answer": "ok",
            "body": "ok",
            "citation": None,
            "category": "help",
            "awaiting_year": False,
            "awaiting_venue": False,
        }
        with patch.object(server, "process_query", return_value=fake):
            response = self.client.post("/api/chat", json={"message": "help"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["body"], "ok")
        self.assertTrue(response.json()["session_id"])

    def test_reset_clears_session(self):
        server._sessions["sess-1"] = [{"query": "hi"}]
        response = self.client.post("/api/reset", json={"session_id": "sess-1"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("sess-1", server._sessions)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["model"], server.MODEL_NAME)
        self.assertIn("provider", payload)


if __name__ == "__main__":
    unittest.main()
