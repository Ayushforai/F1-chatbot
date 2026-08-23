import json
import os

from langchain_community.vectorstores import FAISS

from utils.embeddings import get_embeddings, preload_embeddings
from utils.regulation_parser import (
    extract_regulation_refs,
    is_broad_regulation_query,
    lookup_articles,
)

VECTOR_STORE_ROOT = "./vector_store"
REGULATION_CATEGORIES = frozenset({"general", "sporting", "technical", "financial", "operational"})
_loaded_stores: dict[str, FAISS] = {}
_articles_cache: dict[str, list[dict]] = {}


def warmup_rag(*, categories: list[str] | None = None) -> None:
    """Load embedding weights once and optionally preload FAISS indexes."""
    preload_embeddings()
    if not categories:
        return
    for category in categories:
        try:
            get_vector_store(category)
        except FileNotFoundError:
            continue


def clear_vector_store_cache() -> None:
    """Release cached indexes. Mainly for tests."""
    _loaded_stores.clear()
    _articles_cache.clear()


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


def _load_articles_index(category: str) -> list[dict]:
    if category in _articles_cache:
        return _articles_cache[category]

    path = os.path.join(VECTOR_STORE_ROOT, category, "articles.json")
    if not os.path.isfile(path):
        _articles_cache[category] = []
        return []

    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    articles = payload.get("articles", [])
    _articles_cache[category] = articles
    return articles


def _year_matches(metadata_year: int | None, query_year: int | None) -> bool:
    if query_year is None or metadata_year is None:
        return True
    return metadata_year == query_year


def _dedupe_documents(documents: list) -> list:
    seen: set[tuple] = set()
    unique = []
    for doc in documents:
        metadata = doc.metadata or {}
        key = (
            metadata.get("source"),
            metadata.get("article_id"),
            metadata.get("page"),
            metadata.get("chunk_part"),
            doc.page_content[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def _article_record_to_doc(record: dict):
    from langchain_core.documents import Document

    header = f"ARTICLE {record['article_id']}: {record.get('title', '').strip()}"
    body = record.get("text", "").strip()
    return Document(
        page_content=f"{header}\n{body}".strip(),
        metadata={
            "source": record.get("source"),
            "page": record.get("page"),
            "article_id": record.get("article_id"),
            "article_title": record.get("title"),
            "section": record.get("section"),
            "regulation_year": record.get("regulation_year"),
            "subsection_ids": record.get("subsection_ids", []),
            "lookup": "exact",
        },
    )


def search(category: str, query: str, k: int = 5) -> list[str]:
    contents, _ = search_with_metadata(category, query, k=k)
    return contents


def search_with_metadata(category: str, query: str, k: int = 5) -> tuple[list[str], list[dict]]:
    if category in REGULATION_CATEGORIES:
        return search_regulations(category, query, year=None, k=k)

    store = get_vector_store(category)
    docs = store.similarity_search(query, k=k)
    contents = [doc.page_content for doc in docs]
    metadata = [dict(doc.metadata or {}) for doc in docs]
    return contents, metadata


def search_regulations(
    category: str,
    query: str,
    *,
    year: int | None,
    k: int = 5,
) -> tuple[list[str], list[dict]]:
    """Hybrid regulation search: exact article lookup + vector retrieval."""
    article_refs, section_refs = extract_regulation_refs(query)
    broad = is_broad_regulation_query(query)
    retrieval_k = 20 if broad else max(k, 8 if article_refs or section_refs else k)

    exact_records = lookup_articles(
        _load_articles_index(category),
        article_refs=article_refs,
        section_refs=section_refs,
        regulation_year=year,
    )
    exact_docs = [_article_record_to_doc(record) for record in exact_records[:retrieval_k]]

    store = get_vector_store(category)
    search_query = f"{query} {year}" if year is not None else query
    vector_docs = store.similarity_search(search_query, k=retrieval_k * 2)

    preferred = [
        doc
        for doc in vector_docs
        if _year_matches((doc.metadata or {}).get("regulation_year"), year)
    ]
    if len(preferred) < retrieval_k:
        preferred.extend(doc for doc in vector_docs if doc not in preferred)
    vector_docs = preferred[:retrieval_k]

    if article_refs or section_refs:
        boosted = []
        for doc in vector_docs:
            metadata = doc.metadata or {}
            article_id = str(metadata.get("article_id", "")).upper()
            subsection_ids = {str(value).upper() for value in metadata.get("subsection_ids", [])}
            if any(
                article_id == ref
                or article_id.startswith(f"{ref}.")
                or ref.startswith(f"{article_id}.")
                or ref in subsection_ids
                for ref in article_refs
            ):
                boosted.append(doc)
        vector_docs = _dedupe_documents(boosted + vector_docs)

    merged = _dedupe_documents(exact_docs + vector_docs)[:retrieval_k]
    contents = [doc.page_content for doc in merged]
    metadata = [dict(doc.metadata or {}) for doc in merged]
    return contents, metadata
