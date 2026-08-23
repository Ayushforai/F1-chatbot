import unittest
from unittest.mock import patch

import app
from utils.citations import rag_regulations


class RegulationsYearDefaultTests(unittest.TestCase):
    def test_regulations_year_offer_includes_current_year(self):
        offer = app._regulations_year_offer(2026)
        self.assertIn("2026", offer)
        self.assertIn("different year", offer.lower())

    def test_regulations_rag_search_includes_year(self):
        with patch(
            "app.search_regulations",
            return_value=(["cost cap chunk"], [{"source": "data/financial.pdf", "page": 0, "article_id": "D4"}]),
        ) as search:
            context, source = app._regulations_rag_context("financial", "cost cap", 2026)
        search.assert_called_once_with("financial", "cost cap", year=2026)
        self.assertIn("Season: 2026", context)
        self.assertIn("cost cap chunk", context)
        self.assertIn("financial regulations (2026)", source.label)

    def test_yearless_regulations_defaults_to_current_year(self):
        with patch("app.current_regulations_year", return_value=2026):
            year = app._explicit_year("cost cap") or app.current_regulations_year()
        self.assertEqual(year, 2026)

    def test_explicit_year_skips_offer(self):
        self.assertEqual(app._explicit_year("cost cap in 2024"), 2024)

    def test_generate_f1_response_includes_regulation_year_rule(self):
        with patch("app.ollama.generate", return_value={"response": "answer"}) as generate:
            app.generate_f1_response("cost cap", "context", regulation_year=2026)
        self.assertIn("2026 season regulations", generate.call_args.kwargs["system"])

    def test_handle_regulations_resume_uses_requested_year(self):
        history = [
            {
                "query": "cost cap",
                "category": "financial",
                "awaiting_year": True,
                "pending_kind": "regulations",
                "pending_query": "cost cap",
            }
        ]
        with (
            patch(
                "app._regulations_rag_context",
                return_value=(
                    "Season: 2024\n\nCap was 140M",
                    rag_regulations(category="financial", year=2024, doc_labels=["financial.pdf"]),
                ),
            ) as rag,
            patch("app.generate_f1_response", return_value="The 2024 cost cap was $140M.") as generate,
            patch("app._respond_and_remember") as remember,
        ):
            pending = history[-1]
            category = pending["category"]
            year = app._resolve_pending_year("2024")
            context, _source = app._regulations_rag_context(category, pending["pending_query"], year)
            answer = app.generate_f1_response(
                pending["pending_query"],
                context,
                regulation_year=year,
            )
            app._respond_and_remember(history, "2024", category, answer, year=year)

        rag.assert_called_once_with("financial", "cost cap", 2024)
        generate.assert_called_once()
        remember.assert_called_once()
        self.assertEqual(remember.call_args.kwargs.get("year"), 2024)


if __name__ == "__main__":
    unittest.main()
