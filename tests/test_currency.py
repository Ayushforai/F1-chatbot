import unittest
from unittest.mock import patch

from utils.currency import (
    DEFAULT_USD_TO_GBP,
    DEFAULT_USD_TO_INR,
    apply_currency_display,
    format_money_usd,
    get_exchange_rates,
    is_penalty_context,
    normalize_currencies_in_text,
    refresh_exchange_rates,
)


def _test_rates():
    return {
        "usd_to_inr": DEFAULT_USD_TO_INR,
        "usd_to_gbp": DEFAULT_USD_TO_GBP,
        "eur_to_usd": 1.08,
        "source": "test",
    }


class CurrencyFormatTests(unittest.TestCase):
    def setUp(self):
        self.rates = _test_rates()

    def test_general_money_shows_usd_inr_gbp(self):
        text = "The cost cap is $135 million."
        out = normalize_currencies_in_text(text, penalty=False, rates=self.rates)
        self.assertIn("$135", out)
        self.assertIn("₹", out)
        self.assertIn("£", out)
        self.assertNotIn("€", out)

    def test_penalty_shows_usd_and_inr_only(self):
        text = "Red Bull received a fine of $7 million for a cost cap breach."
        out = normalize_currencies_in_text(
            text,
            user_query="cost cap penalty",
            category="financial",
            penalty=True,
            rates=self.rates,
        )
        self.assertIn("$7", out)
        self.assertIn("₹", out)
        self.assertNotIn("£", out)
        self.assertIn(" for a cost cap", out)

    def test_updated_default_rates_used_in_formatting(self):
        formatted = format_money_usd(1_000_000, penalty=True, rates=self.rates)
        self.assertIn("$1 million", formatted)
        self.assertIn("₹9.57 crore", formatted)  # 1M USD * 95.72 INR

    def test_live_rates_fetch(self):
        payload = {"date": "2026-08-21", "rates": {"INR": 95.72, "GBP": 0.73, "EUR": 0.92}}
        with patch("utils.currency.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = payload
            get.return_value.raise_for_status = lambda: None
            rates = refresh_exchange_rates()
        self.assertEqual(rates["usd_to_inr"], 95.72)
        self.assertEqual(rates["usd_to_gbp"], 0.73)
        self.assertAlmostEqual(rates["eur_to_usd"], 1 / 0.92)

    def test_fallback_when_api_fails(self):
        with patch("utils.currency.requests.get", side_effect=RuntimeError("offline")):
            rates = refresh_exchange_rates()
        self.assertEqual(rates["usd_to_inr"], DEFAULT_USD_TO_INR)
        self.assertEqual(rates["usd_to_gbp"], DEFAULT_USD_TO_GBP)
        self.assertEqual(rates["source"], "fallback")

    def test_get_exchange_rates_uses_cache(self):
        with patch("utils.currency.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {
                "date": "2026-08-21",
                "rates": {"INR": 95.72, "GBP": 0.73, "EUR": 0.92},
            }
            get.return_value.raise_for_status = lambda: None
            refresh_exchange_rates()
            first = get_exchange_rates()
            second = get_exchange_rates()
        self.assertEqual(first["usd_to_inr"], second["usd_to_inr"])
        get.assert_called_once()

    def test_euro_amount_converted_to_allowed_currencies(self):
        text = "The fine was €500,000."
        out = normalize_currencies_in_text(text, penalty=True, rates=self.rates)
        self.assertNotIn("€", out)
        self.assertIn("$", out)
        self.assertIn("₹", out)

    def test_is_penalty_context_detects_fines(self):
        self.assertTrue(is_penalty_context("what was the penalty?", "sporting"))
        self.assertFalse(is_penalty_context("what is the cost cap?", "financial", "The cap is $135m"))

    def test_apply_currency_display_skips_non_money_text(self):
        text = "Max Verstappen won the race in 1:35:21.362."
        self.assertEqual(apply_currency_display(text), text)


if __name__ == "__main__":
    unittest.main()
