import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("F1_SKIP_WARMUP", "1")

import utils.llm as llm


class TestLlmProviderAbstraction(unittest.TestCase):
    def test_default_provider_is_ollama(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "", "LLM_MODEL": ""}, clear=False):
            os.environ.pop("LLM_PROVIDER", None)
            os.environ.pop("LLM_MODEL", None)
            self.assertEqual(llm.get_provider(), "ollama")
            self.assertIn("qwen", llm.get_model_name("ollama"))

    def test_provider_env_override(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-3.8-flash"}, clear=False):
            self.assertEqual(llm.get_provider(), "gemini")
            self.assertEqual(llm.get_model_name(), "gemini-3.8-flash")

    def test_gemini_38_sends_thinking_level(self):
        fake = {
            "candidates": [
                {"content": {"parts": [{"text": "ok"}]}}
            ]
        }
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "test-key",
                "LLM_MODEL": "gemini-3.8-flash",
                "GEMINI_THINKING_LEVEL": "LOW",
            },
            clear=False,
        ), patch("utils.llm.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = fake
            post.return_value.text = "ok"
            result = llm.generate(system="sys", prompt="hi")
        self.assertEqual(result["response"], "ok")
        body = post.call_args.kwargs["json"]
        self.assertEqual(
            body["generationConfig"]["thinkingConfig"]["thinkingLevel"],
            "LOW",
        )

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

    def test_gemini_retries_then_succeeds_on_503(self):
        ok = {"candidates": [{"content": {"parts": [{"text": "recovered"}]}}]}
        fail = Mock(status_code=503, text='{"error":{"message":"high demand"}}')
        success = Mock(status_code=200, text="ok")
        success.json.return_value = ok

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "test-key",
                "LLM_MODEL": "gemini-3.8-flash",
                "LLM_RETRY_ATTEMPTS": "3",
            },
            clear=False,
        ), patch("utils.llm.requests.post", side_effect=[fail, success]) as post, patch(
            "utils.llm.time.sleep"
        ) as sleep:
            result = llm.generate(system="sys", prompt="hi")

        self.assertEqual(result["response"], "recovered")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called()

    def test_gemini_falls_back_to_next_model_after_503(self):
        ok = {"candidates": [{"content": {"parts": [{"text": "from-fallback"}]}}]}
        fail = Mock(status_code=503, text="high demand")
        success = Mock(status_code=200, text="ok")
        success.json.return_value = ok

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "test-key",
                "LLM_MODEL": "gemini-3.8-flash",
                "LLM_RETRY_ATTEMPTS": "1",
                "GEMINI_FALLBACK_MODELS": "gemini-2.0-flash",
            },
            clear=False,
        ), patch("utils.llm.requests.post", side_effect=[fail, success]) as post, patch(
            "utils.llm.time.sleep"
        ):
            result = llm.generate(system="sys", prompt="hi")

        self.assertEqual(result["response"], "from-fallback")
        self.assertEqual(post.call_count, 2)
        first_url = post.call_args_list[0].args[0]
        second_url = post.call_args_list[1].args[0]
        self.assertIn("gemini-3.8-flash", first_url)
        self.assertIn("gemini-2.0-flash", second_url)


if __name__ == "__main__":
    unittest.main()
