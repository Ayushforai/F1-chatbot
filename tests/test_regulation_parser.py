import os
import unittest

from langchain_community.document_loaders import PyPDFLoader

from utils.regulation_parser import (
    classify_regulation_pdf,
    discover_regulation_pdfs,
    extract_regulation_refs,
    is_broad_regulation_query,
    lookup_articles,
    parse_regulation_text,
    regulation_year_from_filename,
    select_pdfs_for_indexing,
    serialize_articles,
)


class RegulationParserTests(unittest.TestCase):
    def test_classify_section_pdfs(self):
        self.assertEqual(
            classify_regulation_pdf(
                "FIA 2026 F1 Regulations - Section A [General Regulatory Provisions] - Iss 01.pdf"
            ),
            "general",
        )
        self.assertEqual(
            classify_regulation_pdf("fia_2026_f1_regulations_-_section_b_sporting_-_iss_05.pdf"),
            "sporting",
        )
        self.assertEqual(
            classify_regulation_pdf("2021_formula_1_technical_regulations_-_2019-10-31.pdf"),
            "technical",
        )
        self.assertEqual(
            classify_regulation_pdf("2021_formula_1_financial_regulations_-_iss_7.pdf"),
            "financial",
        )

    def test_regulation_year_from_filename(self):
        self.assertEqual(
            regulation_year_from_filename(
                "fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_02_-_2026-02-27.pdf"
            ),
            2026,
        )

    def test_select_latest_issue_per_season(self):
        grouped = {
            "sporting": [
                "data/archive/fia_2026_f1_regulations_-_section_b_sporting_-_iss_03_-_2025-07-31.pdf",
                "data/archive/fia_2026_f1_regulations_-_section_b_sporting_-_iss_05_-_2026-02-27.pdf",
            ]
        }
        selected = select_pdfs_for_indexing(grouped)
        self.assertEqual(len(selected["sporting"]), 1)
        self.assertIn("iss_05", os.path.basename(selected["sporting"][0]))

    def test_parse_section_a_pdf_into_articles(self):
        path = (
            "data/archive/fia_2026_f1_regulations_-_section_a_general_provisions_"
            "-_iss_02_-_2026-02-27.pdf"
        )
        if not os.path.isfile(path):
            self.skipTest("Section A PDF not available locally")

        docs = PyPDFLoader(path).load()
        pages = [(doc.metadata.get("page", index), doc.page_content) for index, doc in enumerate(docs)]
        articles = parse_regulation_text(
            pages,
            source=path,
            regulation_year=2026,
            section="A",
        )
        self.assertGreater(len(articles), 3)
        self.assertTrue(any(article.article_id.startswith("A") for article in articles))
        serialized = serialize_articles(articles)
        self.assertIn("subsection_ids", serialized[0])

    def test_parse_legacy_sporting_pdf(self):
        path = "data/archive/2021_formula_1_sporting_regulations_-_2019-10-31.pdf"
        if not os.path.isfile(path):
            self.skipTest("Legacy sporting PDF not available locally")

        docs = PyPDFLoader(path).load()
        pages = [(doc.metadata.get("page", index), doc.page_content) for index, doc in enumerate(docs)]
        articles = parse_regulation_text(
            pages,
            source=path,
            regulation_year=2021,
            section=None,
        )
        article_ids = {article.article_id for article in articles}
        self.assertIn("3", article_ids)

    def test_extract_regulation_refs(self):
        refs, sections = extract_regulation_refs("What does Article B1.1 say in Section B?")
        self.assertIn("B1.1", refs)
        self.assertIn("B", sections)

    def test_lookup_articles_by_subsection(self):
        records = [
            {
                "article_id": "B1",
                "title": "Organisation",
                "text": "B1.1.1 Competitions are reserved...",
                "source": "sporting.pdf",
                "page": 4,
                "regulation_year": 2026,
                "section": "B",
                "subsection_ids": ["B1", "B1.1", "B1.1.1"],
            }
        ]
        matches = lookup_articles(
            records,
            article_refs={"B1.1.1"},
            section_refs=set(),
            regulation_year=2026,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["article_id"], "B1")

    def test_broad_regulation_query_detection(self):
        self.assertTrue(is_broad_regulation_query("List every rule about the cost cap"))
        self.assertFalse(is_broad_regulation_query("What does Article D2.1 say?"))

    def test_discover_regulation_pdfs_finds_archive_files(self):
        grouped = discover_regulation_pdfs()
        if not os.path.isdir("data/archive"):
            self.skipTest("Archive directory not available locally")
        self.assertTrue(any(grouped["general"]))
        self.assertTrue(any(grouped["sporting"]))


if __name__ == "__main__":
    unittest.main()
