import unittest

from utils import chat_store


class TestChatStoreMemory(unittest.TestCase):
    def setUp(self):
        chat_store.clear_memory_for_tests()

    def tearDown(self):
        chat_store.clear_memory_for_tests()

    def test_load_save_roundtrip(self):
        history = chat_store.load_history("sess-mem")
        self.assertEqual(history, [])
        history.append({"query": "hello", "category": "help", "answer": "hi"})
        chat_store.save_history("sess-mem", history)
        again = chat_store.load_history("sess-mem")
        self.assertEqual(again[0]["query"], "hello")

    def test_reset_one_session(self):
        hist = chat_store.load_history("keep")
        hist.append({"query": "a"})
        chat_store.save_history("keep", hist)
        other = chat_store.load_history("drop")
        other.append({"query": "b"})
        chat_store.save_history("drop", other)
        chat_store.reset_session("drop")
        self.assertIn("keep", chat_store.memory_sessions())
        self.assertNotIn("drop", chat_store.memory_sessions())


if __name__ == "__main__":
    unittest.main()
