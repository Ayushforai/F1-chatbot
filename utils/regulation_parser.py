"""Parse FIA regulation PDFs into section/article chunks for RAG and exact lookup."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

ARTICLE_HEADER_RE = re.compile(
    r"(?:^|\n)\s*ARTICLE\s+([A-Z]?\d+[A-Z]?)\s*[:\-]\s*(.+?)(?=\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
SUBSECTION_ID_RE = re.compile(r"\b([A-Z]\d+(?:\.\d+)+|\d+\.\d+(?:\.\d+)*)\b")
ISSUE_RE = re.compile(r"(?:iss(?:ue)?[_\s-]*)(\d+)", re.IGNORECASE)
DATE_RE = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")
YEAR_RE = re.compile(r"(20\d{2})")

CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "general",
        (
            r"section[_\s-]*a",
            r"general[_\s-]*regulatory",
            r"general[_\s-]*provision",
        ),
    ),
    ("sporting", (r"section[_\s-]*b", r"sporting")),
    ("technical", (r"section[_\s-]*c", r"technical")),
    ("financial", (r"section[_\s-]*d", r"section[_\s-]*e", r"financial")),
    ("operational", (r"operational",)),
]

SECTION_FROM_FILENAME_RE = re.compile(r"section[_\s-]*([a-e])", re.IGNORECASE)

PDF_SEARCH_DIRS = ("./data", "./data/archive")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


@dataclass(frozen=True)
class ParsedArticle:
    article_id: str
    title: str
    text: str
    page: int
    source: str
    regulation_year: int | None
    section: str | None
    subsection_ids: tuple[str, ...]


def classify_regulation_pdf(filename: str) -> str | None:
    """Map a PDF filename to a regulation index category."""
    name = filename.lower()
    for category, patterns in CATEGORY_PATTERNS:
        if any(re.search(pattern, name) for pattern in patterns):
            return category
    return None


def regulation_year_from_filename(filename: str) -> int | None:
    match = YEAR_RE.search(filename)
    return int(match.group(1)) if match else None


def section_from_filename(filename: str) -> str | None:
    match = SECTION_FROM_FILENAME_RE.search(filename.lower())
    return match.group(1).upper() if match else None


def pdf_priority_key(filename: str) -> tuple[int, str, int]:
    """Prefer newer seasons, later issue numbers, and later publish dates."""
    year = regulation_year_from_filename(filename) or 0
    issue_match = ISSUE_RE.search(filename)
    issue = int(issue_match.group(1)) if issue_match else 0
    date_match = DATE_RE.search(filename)
    date = date_match.group(0) if date_match else ""
    return (year, date, issue)


def discover_regulation_pdfs() -> dict[str, list[str]]:
    """Return PDF paths grouped by category from data/ and data/archive/."""
    grouped: dict[str, list[str]] = {category: [] for category, _ in CATEGORY_PATTERNS}

    for directory in PDF_SEARCH_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.lower().endswith(".pdf"):
                continue
            category = classify_regulation_pdf(name)
            if category is None:
                continue
            grouped[category].append(os.path.join(directory, name))

    return grouped


def select_pdfs_for_indexing(grouped: dict[str, list[str]]) -> dict[str, list[str]]:
    """Keep the latest issue PDF for each category/season pair."""
    selected: dict[str, list[str]] = {}
    for category, paths in grouped.items():
        if not paths:
            continue
        by_year: dict[int, list[str]] = {}
        for path in paths:
            year = regulation_year_from_filename(os.path.basename(path)) or 0
            by_year.setdefault(year, []).append(path)
        selected[category] = [
            max(year_paths, key=lambda path: pdf_priority_key(os.path.basename(path)))
            for year_paths in by_year.values()
        ]
    return selected


def _subsection_ids(text: str, article_id: str) -> tuple[str, ...]:
    ids = {article_id.upper()}
    article_prefix = article_id.upper()
    for match in SUBSECTION_ID_RE.finditer(text):
        candidate = match.group(1).upper()
        if candidate.startswith(article_prefix) or candidate.split(".", 1)[0] == article_prefix:
            ids.add(candidate)
        elif article_prefix.isdigit() and candidate.split(".", 1)[0] == article_prefix:
            ids.add(candidate)
    return tuple(sorted(ids, key=lambda value: (len(value.split(".")), value)))


def parse_regulation_text(
    pages: list[tuple[int, str]],
    *,
    source: str,
    regulation_year: int | None,
    section: str | None,
) -> list[ParsedArticle]:
    """Split regulation pages into article-level records."""
    if not pages:
        return []

    page_starts: list[tuple[int, int]] = []
    combined_parts: list[str] = []
    offset = 0
    for page_num, text in pages:
        page_starts.append((offset, page_num))
        combined_parts.append(text)
        offset += len(text) + 1
    combined = "\n".join(combined_parts)

    matches = list(ARTICLE_HEADER_RE.finditer(combined))
    if not matches:
        fallback_page = pages[0][0]
        return [
            ParsedArticle(
                article_id="document",
                title=os.path.basename(source),
                text=combined.strip(),
                page=fallback_page,
                source=source,
                regulation_year=regulation_year,
                section=section,
                subsection_ids=("document",),
            )
        ]

    articles: list[ParsedArticle] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(combined)
        article_id = match.group(1).upper()
        title = match.group(2).strip()
        body = combined[start:end].strip()
        page = _page_for_offset(page_starts, start)
        article_section = section or (article_id[0] if article_id[:1].isalpha() else None)
        articles.append(
            ParsedArticle(
                article_id=article_id,
                title=title,
                text=body,
                page=page,
                source=source,
                regulation_year=regulation_year,
                section=article_section,
                subsection_ids=_subsection_ids(body, article_id),
            )
        )
    return articles


def _page_for_offset(page_starts: list[tuple[int, int]], offset: int) -> int:
    page = page_starts[0][1]
    for start, page_num in page_starts:
        if start <= offset:
            page = page_num
        else:
            break
    return page


def articles_to_documents(articles: list[ParsedArticle]) -> list[Document]:
    """Convert parsed articles into LangChain documents, splitting long bodies."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    documents: list[Document] = []

    for article in articles:
        metadata = {
            "source": article.source,
            "page": article.page,
            "article_id": article.article_id,
            "article_title": article.title,
            "section": article.section,
            "regulation_year": article.regulation_year,
            "subsection_ids": list(article.subsection_ids),
        }
        if len(article.text) <= CHUNK_SIZE:
            documents.append(Document(page_content=article.text, metadata=metadata))
            continue

        chunks = splitter.split_text(article.text)
        for chunk_index, chunk in enumerate(chunks):
            chunk_metadata = dict(metadata)
            chunk_metadata["chunk_part"] = chunk_index + 1
            documents.append(Document(page_content=chunk, metadata=chunk_metadata))

    return documents


def serialize_articles(articles: list[ParsedArticle]) -> list[dict]:
    return [
        {
            "article_id": article.article_id,
            "title": article.title,
            "text": article.text,
            "page": article.page,
            "source": article.source,
            "regulation_year": article.regulation_year,
            "section": article.section,
            "subsection_ids": list(article.subsection_ids),
        }
        for article in articles
    ]


def save_articles_index(category: str, articles: list[ParsedArticle], output_dir: str) -> str:
    path = os.path.join(output_dir, category, "articles.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"articles": serialize_articles(articles)}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


ARTICLE_REF_RE = re.compile(
    r"(?:\b(?:article|art\.?)\s*([A-Z]?\d+(?:\.\d+)*)\b)|"
    r"(\b[A-Z]\d+(?:\.\d+)+\b)|"
    r"(\b\d+\.\d+(?:\.\d+)*\b)",
    re.IGNORECASE,
)
SECTION_REF_RE = re.compile(r"\bsection\s+([A-E])\b", re.IGNORECASE)

BROAD_REGULATION_PHRASES = (
    "every rule",
    "all rules",
    "list all",
    "list every",
    "what are the rules",
    "overview of",
    "summarize",
    "summary of",
    "general principles",
    "all provisions",
    "full rule",
)


def extract_regulation_refs(query: str) -> tuple[set[str], set[str]]:
    """Return article/subsection refs and section letters mentioned in a query."""
    article_refs: set[str] = set()
    for match in ARTICLE_REF_RE.finditer(query):
        ref = next(group for group in match.groups() if group)
        article_refs.add(ref.upper())

    section_refs = {match.group(1).upper() for match in SECTION_REF_RE.finditer(query)}
    return article_refs, section_refs


def is_broad_regulation_query(query: str) -> bool:
    lowered = query.lower()
    if any(phrase in lowered for phrase in BROAD_REGULATION_PHRASES):
        return True
    article_refs, _ = extract_regulation_refs(query)
    return len(lowered.split()) >= 8 and not article_refs


def lookup_articles(
    articles: list[dict],
    *,
    article_refs: set[str],
    section_refs: set[str],
    regulation_year: int | None,
) -> list[dict]:
    """Exact lookup against the structured articles index."""
    if not articles or (not article_refs and not section_refs):
        return []

    matches: list[dict] = []
    seen: set[str] = set()

    def _year_ok(record: dict) -> bool:
        record_year = record.get("regulation_year")
        if regulation_year is None or record_year is None:
            return True
        return record_year == regulation_year

    for record in articles:
        if not _year_ok(record):
            continue

        record_section = (record.get("section") or "").upper()
        if section_refs and record_section not in section_refs:
            continue

        record_id = str(record.get("article_id", "")).upper()
        subsection_ids = {str(value).upper() for value in record.get("subsection_ids", [])}

        matched = False
        if article_refs:
            for ref in article_refs:
                if (
                    record_id == ref
                    or record_id.startswith(f"{ref}.")
                    or ref.startswith(f"{record_id}.")
                    or ref in subsection_ids
                ):
                    matched = True
                    break
        elif section_refs:
            matched = True

        if not matched:
            continue

        key = f"{record.get('source')}::{record_id}"
        if key in seen:
            continue
        seen.add(key)
        matches.append(record)

    return matches
