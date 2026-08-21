import os
import unittest
from unittest.mock import patch

from utils.embeddings import _hf_token, get_embeddings


class EmbeddingAuthTests(unittest.TestCase):
    def test_hf_token_prefers_hf_token_env(self):
        with patch.dict(os.environ, {"HF_TOKEN": "hf_test", "HUGGING_FACE_HUB_TOKEN": "other"}, clear=False):
            self.assertEqual(_hf_token(), "hf_test")

    def test_hf_token_falls_back_to_hub_token(self):
        env = os.environ.copy()
        env.pop("HF_TOKEN", None)
        with patch.dict(os.environ, {**env, "HUGGING_FACE_HUB_TOKEN": "hf_hub"}, clear=True):
            self.assertEqual(_hf_token(), "hf_hub")

    @patch("utils.embeddings.HuggingFaceEmbeddings")
    def test_get_embeddings_passes_token_when_set(self, mock_embeddings):
        with patch.dict(os.environ, {"HF_TOKEN": "hf_test"}, clear=False):
            get_embeddings()
        model_kwargs = mock_embeddings.call_args.kwargs["model_kwargs"]
        self.assertEqual(model_kwargs["token"], "hf_test")
        self.assertEqual(model_kwargs["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
