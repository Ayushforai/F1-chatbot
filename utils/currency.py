"""Format monetary values in USD, INR, and GBP only."""

from __future__ import annotations

import re
import time
from typing import TypedDict

import requests

# Fallback rates when the live FX API is unavailable.
DEFAULT_USD_TO_INR = 95.72
DEFAULT_USD_TO_GBP = 0.73
DEFAULT_EUR_TO_USD = 1.08

FX_API_URL = "https://api.frankfurter.app/latest"
FX_CACHE_TTL_SECONDS = 3600  # refresh at most once per hour

PENALTY_HINTS = (
    "fine",
    "fines",
    "penalty",
    "penalties",
    "penalised",
    "penalized",
    "cost cap breach",
    "budget cap breach",
    "breach",
    "sanction",
    "infringement",
    "punished",
    "deduction",
    "forfeit",
    "violation",
)


class ExchangeRates(TypedDict):
    usd_to_inr: float
    usd_to_gbp: float
    eur_to_usd: float
    source: str


_rates_cache: ExchangeRates | None = None
_rates_cached_at: float = 0.0


def _fallback_rates() -> ExchangeRates:
    return {
        "usd_to_inr": DEFAULT_USD_TO_INR,
        "usd_to_gbp": DEFAULT_USD_TO_GBP,
        "eur_to_usd": DEFAULT_EUR_TO_USD,
        "source": "fallback",
    }


def _fetch_live_rates() -> ExchangeRates:
    response = requests.get(
        FX_API_URL,
        params={"from": "USD", "to": "INR,GBP,EUR"},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    rates = payload.get("rates", {})
    inr = float(rates["INR"])
    gbp = float(rates["GBP"])
    eur_per_usd = float(rates["EUR"])
    return {
        "usd_to_inr": inr,
        "usd_to_gbp": gbp,
        "eur_to_usd": 1.0 / eur_per_usd if eur_per_usd else DEFAULT_EUR_TO_USD,
        "source": f"live:{payload.get('date', 'latest')}",
    }


def get_exchange_rates(*, force_refresh: bool = False) -> ExchangeRates:
    """Return cached USD→INR/GBP rates, refreshing from Frankfurter when stale."""
    global _rates_cache, _rates_cached_at

    now = time.time()
    if (
        not force_refresh
        and _rates_cache is not None
        and now - _rates_cached_at < FX_CACHE_TTL_SECONDS
    ):
        return _rates_cache

    try:
        _rates_cache = _fetch_live_rates()
        _rates_cached_at = now
    except Exception as exc:
        print(f" [FX Warning] Using fallback currency rates ({exc}).")
        _rates_cache = _fallback_rates()
        _rates_cached_at = now

    return _rates_cache


def refresh_exchange_rates() -> ExchangeRates:
    """Force-refresh exchange rates (called on app startup)."""
    return get_exchange_rates(force_refresh=True)


def get_currency_prompt_rules() -> str:
    rates = get_exchange_rates()
    return (
        "CURRENCY RULES:\n"
        "- Use ONLY US dollars (USD), Indian rupees (INR), and UK pounds (GBP). "
        "Never show euros or any other currency.\n"
        "- For fines, penalties, and cost-cap sanctions: show USD and INR together, "
        'e.g. "$500,000 (₹47.9 million)".\n'
        "- For other monetary amounts (budget limits, cap levels, spending): show USD, INR, and GBP, "
        'e.g. "$135 million / ₹12,922 million / £98.6 million".\n'
        f"- Use these display rates when converting: 1 USD = {rates['usd_to_inr']:.2f} INR, "
        f"1 USD = {rates['usd_to_gbp']:.2f} GBP.\n"
    )


_MONEY_PATTERN = re.compile(
    r"""
    (?P<full>
        (?:
            (?P<prefix_curr>\$|€|£|₹|USD|EUR|GBP|INR|Rs\.?)\s*
        )?
        (?P<amount>[\d]{1,3}(?:,\d{3})*|\d+(?:\.\d+)?)
        \s*
        (?P<scale>million|millions|mn|m|bn|billion|billions|b|k|thousand|thousands|crore|crores|lakh|lakhs)?
        (?P<suffix_curr>dollars?|usd|euros?|eur|pounds?|sterling|gbp|rupees?|inr)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _currency_symbol_to_usd(rates: ExchangeRates) -> dict[str, float]:
    return {
        "$": 1.0,
        "usd": 1.0,
        "dollar": 1.0,
        "dollars": 1.0,
        "€": rates["eur_to_usd"],
        "eur": rates["eur_to_usd"],
        "euro": rates["eur_to_usd"],
        "euros": rates["eur_to_usd"],
        "£": 1.0 / rates["usd_to_gbp"] if rates["usd_to_gbp"] else 1.0,
        "gbp": 1.0 / rates["usd_to_gbp"] if rates["usd_to_gbp"] else 1.0,
        "pound": 1.0 / rates["usd_to_gbp"] if rates["usd_to_gbp"] else 1.0,
        "pounds": 1.0 / rates["usd_to_gbp"] if rates["usd_to_gbp"] else 1.0,
        "sterling": 1.0 / rates["usd_to_gbp"] if rates["usd_to_gbp"] else 1.0,
        "₹": 1.0 / rates["usd_to_inr"] if rates["usd_to_inr"] else 1.0,
        "inr": 1.0 / rates["usd_to_inr"] if rates["usd_to_inr"] else 1.0,
        "rupee": 1.0 / rates["usd_to_inr"] if rates["usd_to_inr"] else 1.0,
        "rupees": 1.0 / rates["usd_to_inr"] if rates["usd_to_inr"] else 1.0,
        "rs": 1.0 / rates["usd_to_inr"] if rates["usd_to_inr"] else 1.0,
        "rs.": 1.0 / rates["usd_to_inr"] if rates["usd_to_inr"] else 1.0,
    }


def _scale_multiplier(scale: str | None) -> float:
    if not scale:
        return 1.0
    key = scale.lower()
    if key in {"k", "thousand", "thousands"}:
        return 1_000.0
    if key in {"m", "mn", "million", "millions"}:
        return 1_000_000.0
    if key in {"b", "bn", "billion", "billions"}:
        return 1_000_000_000.0
    if key in {"lakh", "lakhs"}:
        return 100_000.0
    if key in {"crore", "crores"}:
        return 10_000_000.0
    return 1.0


def _parse_amount_to_usd(
    amount: str,
    scale: str | None,
    prefix_curr: str | None,
    suffix_curr: str | None,
    rates: ExchangeRates,
) -> float | None:
    try:
        value = float(amount.replace(",", ""))
    except ValueError:
        return None

    value *= _scale_multiplier(scale)

    symbol_rates = _currency_symbol_to_usd(rates)
    currency_key = (prefix_curr or suffix_curr or "$").lower().strip()
    rate = symbol_rates.get(currency_key, 1.0)
    return value * rate


def _format_usd(usd: float) -> str:
    if usd >= 1_000_000_000:
        return f"${usd / 1_000_000_000:.2f} billion".replace(".00 billion", " billion")
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.2f} million".replace(".00 million", " million")
    if usd >= 1_000:
        return f"${usd:,.0f}"
    if abs(usd - round(usd)) < 0.01:
        return f"${usd:,.0f}"
    return f"${usd:,.2f}"


def _format_inr(amount_inr: float) -> str:
    if amount_inr >= 10_000_000:
        return f"₹{amount_inr / 10_000_000:.2f} crore".replace(".00 crore", " crore")
    if amount_inr >= 1_000_000:
        return f"₹{amount_inr / 1_000_000:.2f} million".replace(".00 million", " million")
    if amount_inr >= 100_000:
        return f"₹{amount_inr / 100_000:.2f} lakh".replace(".00 lakh", " lakh")
    if abs(amount_inr - round(amount_inr)) < 0.01:
        return f"₹{amount_inr:,.0f}"
    return f"₹{amount_inr:,.2f}"


def _format_gbp(amount_gbp: float) -> str:
    if amount_gbp >= 1_000_000_000:
        return f"£{amount_gbp / 1_000_000_000:.2f} billion".replace(".00 billion", " billion")
    if amount_gbp >= 1_000_000:
        return f"£{amount_gbp / 1_000_000:.2f} million".replace(".00 million", " million")
    if amount_gbp >= 1_000:
        return f"£{amount_gbp:,.0f}"
    if abs(amount_gbp - round(amount_gbp)) < 0.01:
        return f"£{amount_gbp:,.0f}"
    return f"£{amount_gbp:,.2f}"


def format_money_usd(usd: float, *, penalty: bool = False, rates: ExchangeRates | None = None) -> str:
    rates = rates or get_exchange_rates()
    inr = usd * rates["usd_to_inr"]
    gbp = usd * rates["usd_to_gbp"]
    if penalty:
        return f"{_format_usd(usd)} ({_format_inr(inr)})"
    return f"{_format_usd(usd)} / {_format_inr(inr)} / {_format_gbp(gbp)}"


def is_penalty_context(user_query: str = "", category: str = "", text: str = "") -> bool:
    blob = f"{user_query} {category} {text}".lower()
    return any(hint in blob for hint in PENALTY_HINTS)


def _looks_like_money_match(match: re.Match[str]) -> bool:
    prefix = match.group("prefix_curr")
    suffix = match.group("suffix_curr")
    scale = match.group("scale")
    amount = match.group("amount")
    if prefix or suffix or scale:
        return True
    return "," in amount


def normalize_currencies_in_text(
    text: str,
    *,
    user_query: str = "",
    category: str = "",
    penalty: bool | None = None,
    rates: ExchangeRates | None = None,
) -> str:
    """Rewrite monetary amounts to USD/INR/GBP (penalties: USD + INR only)."""
    rates = rates or get_exchange_rates()
    if penalty is None:
        penalty = is_penalty_context(user_query, category, text)

    matches = list(_MONEY_PATTERN.finditer(text))
    if not matches:
        return text

    parts: list[str] = []
    last = 0
    for match in matches:
        if not _looks_like_money_match(match):
            continue
        usd = _parse_amount_to_usd(
            match.group("amount"),
            match.group("scale"),
            match.group("prefix_curr"),
            match.group("suffix_curr"),
            rates,
        )
        if usd is None or usd <= 0:
            continue
        parts.append(text[last:match.start()])
        parts.append(format_money_usd(usd, penalty=penalty, rates=rates))
        last = match.end()

    if not parts:
        return text

    parts.append(text[last:])
    return "".join(parts)


def apply_currency_display(text: str, *, user_query: str = "", category: str = "") -> str:
    if not re.search(r"[\$€£₹]|USD|EUR|GBP|INR|\b(?:fine|penalty|cost cap)\b", text, re.I):
        return text
    return normalize_currencies_in_text(text, user_query=user_query, category=category)
