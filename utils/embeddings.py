import torch
from langchain_huggingface import HuggingFaceEmbeddings

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"


def get_embeddings() -> HuggingFaceEmbeddings:
    # CPU avoids MPS instability with sentence-transformers on macOS.
    device = "cpu"
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )
