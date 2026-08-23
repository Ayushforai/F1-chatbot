import unittest

from utils.citations import (
    SourceCitation,
    append_citation,
    citation_from_historical_metadata,
    citation_from_regulation_metadata,
    csv_driver_teams,
    csv_race_results,
    openf1_api,
)


class CitationTests(unittest.TestCase):
    def test_append_citation(self):
        answer = append_citation("The cost cap is $135m.", csv_driver_teams(year=2012))
        self.assertIn("— Source:", answer)
        self.assertIn("2012 season", answer)

    def test_no_duplicate_citation(self):
        source = csv_race_results(year=2021, venue="Monaco")
        once = append_citation("Answer", source)
        twice = append_citation(once, source)
        self.assertEqual(once.count("— Source:"), 1)
        self.assertEqual(twice.count("— Source:"), 1)

    def test_openf1_citation(self):
        source = openf1_api(endpoint="lap 12", detail="2024 Monaco")
        self.assertIn("OpenF1 API", source.format())

    def test_historical_rag_citation(self):
        source = citation_from_historical_metadata(
            [{"year": 2008, "race": "British Grand Prix", "round": 9}]
        )
        self.assertIn("2008 British Grand Prix", source.label)

    def test_regulation_rag_citation(self):
        source = citation_from_regulation_metadata(
            "financial",
            2026,
            [
                {
                    "source": "data/2026_FIA_F1_Financial_Regulations.pdf",
                    "page": 4,
                    "article_id": "D4",
                }
            ],
        )
        self.assertIn("financial regulations (2026)", source.label)
        self.assertIn("Financial_Regulations.pdf, Art. D4, p. 5", source.label)

    def test_respond_and_remember_appends_citation(self):
        import app

        history: list[dict] = []
        with unittest.mock.patch("builtins.print"):
            app._respond_and_remember(
                history,
                "Which team did Hamilton drive for in 2012?",
                "historical",
                "McLaren all season.",
                source=csv_driver_teams(year=2012),
            )
        self.assertIn("— Source:", history[-1]["answer"])
        self.assertIn("2012 season", history[-1]["answer"])


if __name__ == "__main__":
    unittest.main()
