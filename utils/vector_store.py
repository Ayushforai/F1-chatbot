import os
from langchain_community.vectorstores import FAISS
from utils.embeddings import get_embeddings

VECTOR_STORE_ROOT = "./vector_store"
_loaded_stores: dict[str, FAISS] = {}


def get_vector_store(category: str) -> FAISS:
    if category in _loaded_stores:
        return _loaded_stores[category]

    index_path = os.path.join(VECTOR_STORE_ROOT, category)
    if not os.path.isdir(index_path):
        raise FileNotFoundError(
            f"Index directory '{index_path}' not found. "
            f"Run the appropriate processor script first."
        )

    embeddings = get_embeddings()
    store = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    _loaded_stores[category] = store
    return store


def search(category: str, query: str, k: int = 5) -> list[str]:
    store = get_vector_store(category)
    docs = store.similarity_search(query, k=k)
    return [doc.page_content for doc in docs]
