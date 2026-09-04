import os
import unittest
from unittest.mock import patch

os.environ.setdefault("F1_SKIP_WARMUP", "1")

import utils.llm as llm


class TestLlmProviderAbstraction(unittest.TestCase):
    def test_default_provider_is_ollama(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": ""}, clear=False):
            os.environ.pop("LLM_PROVIDER", None)
            self.assertEqual(llm.get_provider(), "ollama")
            self.assertIn("qwen", llm.get_model_name("ollama"))

    def test_provider_env_override(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-3.6-flash"}, clear=False):
            self.assertEqual(llm.get_provider(), "gemini")
            self.assertEqual(llm.get_model_name(), "gemini-3.6-flash")

    def test_gemini_requires_api_key(self):
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "", "LLM_API_KEY": ""},
            clear=False,
        ):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("LLM_API_KEY", None)
            with self.assertRaises(RuntimeError):
                llm.generate(system="sys", prompt="hi")

    def test_openai_compatible_posts_chat_completions(self):
        fake = {
            "choices": [{"message": {"content": '{"query_type":"live_telemetry"}'}}]
        }
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "groq",
                "GROQ_API_KEY": "test-key",
                "LLM_MODEL": "llama-3.3-70b-versatile",
            },
            clear=False,
        ), patch("utils.llm.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = fake
            post.return_value.text = "ok"
            result = llm.generate(
                system="extract",
                prompt="telemetry for #1",
                format="json",
                options={"temperature": 0.0},
            )
        self.assertEqual(result["response"], '{"query_type":"live_telemetry"}')
        args, kwargs = post.call_args
        self.assertIn("chat/completions", args[0])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})

    def test_describe_config_includes_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x"}, clear=False):
            cfg = llm.describe_config()
        self.assertEqual(cfg["provider"], "openai")
        self.assertEqual(cfg["has_api_key"], "yes")


if __name__ == "__main__":
    unittest.main()
