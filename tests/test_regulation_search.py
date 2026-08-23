import json
import os
import tempfile
import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from utils.vector_store import search_regulations


class RegulationSearchTests(unittest.TestCase):
    def test_search_regulations_prefers_exact_article_lookup(self):
        articles = [
            {
                "article_id": "A1",
                "title": "General Principles",
                "text": "ARTICLE A1: GENERAL PRINCIPLES\nA1.1 Overview",
                "source": "section_a.pdf",
                "page": 4,
                "regulation_year": 2026,
                "section": "A",
                "subsection_ids": ["A1", "A1.1"],
            }
        ]
        fake_doc = Document(
            page_content="Unrelated chunk",
            metadata={"source": "other.pdf", "page": 1, "article_id": "B9"},
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "utils.vector_store.VECTOR_STORE_ROOT", tmpdir
        ), patch("utils.vector_store.get_vector_store") as get_store, patch(
            "utils.vector_store._load_articles_index", return_value=articles
        ):
            get_store.return_value.similarity_search.return_value = [fake_doc]
            os.makedirs(os.path.join(tmpdir, "general"))
            with open(os.path.join(tmpdir, "general", "articles.json"), "w", encoding="utf-8") as handle:
                json.dump({"articles": articles}, handle)

            contents, metadata = search_regulations(
                "general",
                "What does Article A1.1 say?",
                year=2026,
                k=5,
            )

        self.assertIn("ARTICLE A1", contents[0])
        self.assertEqual(metadata[0]["article_id"], "A1")
        self.assertEqual(metadata[0]["lookup"], "exact")

    def test_broad_query_requests_more_chunks(self):
        with patch("utils.vector_store.lookup_articles", return_value=[]), patch(
            "utils.vector_store.get_vector_store"
        ) as get_store, patch("utils.vector_store._load_articles_index", return_value=[]):
            get_store.return_value.similarity_search.return_value = [
                Document(page_content=f"chunk {index}", metadata={"page": index})
                for index in range(25)
            ]
            search_regulations(
                "sporting",
                "List every rule about the safety car",
                year=2026,
                k=5,
            )
            requested_k = get_store.return_value.similarity_search.call_args.kwargs["k"]
            self.assertGreaterEqual(requested_k, 20)


if __name__ == "__main__":
    unittest.main()
