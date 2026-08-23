import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

_embeddings: HuggingFaceEmbeddings | None = None


def _hf_token() -> str | None:
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    if token:
        os.environ.setdefault("HF_TOKEN", token)
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)
    return token


def _build_embeddings() -> HuggingFaceEmbeddings:
    # CPU avoids MPS instability with sentence-transformers on macOS.
    model_kwargs: dict = {"device": "cpu"}
    token = _hf_token()
    if token:
        model_kwargs["token"] = token

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs=model_kwargs,
        encode_kwargs={"normalize_embeddings": True},
    )


def get_embeddings() -> HuggingFaceEmbeddings:
    """Return a process-wide cached embedding model (weights load once)."""
    global _embeddings
    if _embeddings is None:
        _embeddings = _build_embeddings()
    return _embeddings


def preload_embeddings() -> HuggingFaceEmbeddings:
    """Eagerly load embedding weights. Call once at process startup."""
    return get_embeddings()


def clear_embeddings_cache() -> None:
    """Release the cached model. Mainly for tests."""
    global _embeddings
    _embeddings = None
