"""Map user/extractor venue synonyms to OpenF1 country_name + location."""

from __future__ import annotations

import re

# OpenF1 `country_name` values (2024 calendar and later).
CANONICAL_COUNTRIES = {
    "Australia",
    "Austria",
    "Azerbaijan",
    "Bahrain",
    "Belgium",
    "Brazil",
    "Canada",
    "China",
    "Hungary",
    "Italy",
    "Japan",
    "Mexico",
    "Monaco",
    "Netherlands",
    "Qatar",
    "Saudi Arabia",
    "Singapore",
    "Spain",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
}

# Countries that host more than one Grand Prix. Users must name the race/circuit.
MULTI_GP_COUNTRIES = {
    "Italy": [
        ("Emilia Romagna Grand Prix", "Imola"),
        ("Italian Grand Prix", "Monza"),
    ],
    "United States": [
        ("Miami Grand Prix", "Miami"),
        ("United States Grand Prix", "Austin"),
        ("Las Vegas Grand Prix", "Las Vegas"),
    ],
}

# Lowercase synonym -> OpenF1 country_name (single-GP, or ambiguous multi-GP).
COUNTRY_SYNONYMS = {
    "australia": "Australia",
    "australian": "Australia",
    "melbourne": "Australia",
    "albert park": "Australia",
    "austria": "Austria",
    "austrian": "Austria",
    "spielberg": "Austria",
    "red bull ring": "Austria",
    "azerbaijan": "Azerbaijan",
    "baku": "Azerbaijan",
    "bahrain": "Bahrain",
    "sakhir": "Bahrain",
    "belgium": "Belgium",
    "belgian": "Belgium",
    "spa": "Belgium",
    "spa francorchamps": "Belgium",
    "brazil": "Brazil",
    "brazilian": "Brazil",
    "sao paulo": "Brazil",
    "são paulo": "Brazil",
    "interlagos": "Brazil",
    "canada": "Canada",
    "canadian": "Canada",
    "montreal": "Canada",
    "montréal": "Canada",
    "china": "China",
    "chinese": "China",
    "shanghai": "China",
    "hungary": "Hungary",
    "hungarian": "Hungary",
    "hungaroring": "Hungary",
    "budapest": "Hungary",
    "italy": "Italy",
    "italian": "Italy",
    "japan": "Japan",
    "japanese": "Japan",
    "suzuka": "Japan",
    "mexico": "Mexico",
    "mexican": "Mexico",
    "mexico city": "Mexico",
    "monaco": "Monaco",
    "monte carlo": "Monaco",
    "monte-carlo": "Monaco",
    "netherlands": "Netherlands",
    "dutch": "Netherlands",
    "holland": "Netherlands",
    "zandvoort": "Netherlands",
    "qatar": "Qatar",
    "lusail": "Qatar",
    "losail": "Qatar",
    "saudi arabia": "Saudi Arabia",
    "saudi": "Saudi Arabia",
    "saudi arabian": "Saudi Arabia",
    "jeddah": "Saudi Arabia",
    "singapore": "Singapore",
    "marina bay": "Singapore",
    "spain": "Spain",
    "spanish": "Spain",
    "barcelona": "Spain",
    "catalunya": "Spain",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates",
    "yas marina": "United Arab Emirates",
    "yas island": "United Arab Emirates",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "british": "United Kingdom",
    "england": "United Kingdom",
    "uk": "United Kingdom",
    "silverstone": "United Kingdom",
    "united states": "United States",
    "usa": "United States",
    "america": "United States",
    "american": "United States",
}

# Longer / more specific phrases win. Maps to (country, location).
# location is the OpenF1 `location` field when the country has multiple GPs.
GP_ALIASES: list[tuple[str, str, str | None]] = [
    ("emilia romagna grand prix", "Italy", "Imola"),
    ("emilia-romagna grand prix", "Italy", "Imola"),
    ("emilia romagna gp", "Italy", "Imola"),
    ("emilia romagna", "Italy", "Imola"),
    ("italian grand prix", "Italy", "Monza"),
    ("italian gp", "Italy", "Monza"),
    ("united states grand prix", "United States", "Austin"),
    ("united states gp", "United States", "Austin"),
    ("us grand prix", "United States", "Austin"),
    ("us gp", "United States", "Austin"),
    ("las vegas grand prix", "United States", "Las Vegas"),
    ("las vegas gp", "United States", "Las Vegas"),
    ("miami grand prix", "United States", "Miami"),
    ("miami gp", "United States", "Miami"),
    ("british grand prix", "United Kingdom", "Silverstone"),
    ("british gp", "United Kingdom", "Silverstone"),
    ("abu dhabi grand prix", "United Arab Emirates", "Yas Island"),
    ("abu dhabi gp", "United Arab Emirates", "Yas Island"),
    ("sao paulo grand prix", "Brazil", "São Paulo"),
    ("são paulo grand prix", "Brazil", "São Paulo"),
    ("imola", "Italy", "Imola"),
    ("monza", "Italy", "Monza"),
    ("miami", "United States", "Miami"),
    ("austin", "United States", "Austin"),
    ("cota", "United States", "Austin"),
    ("circuit of the americas", "United States", "Austin"),
    ("las vegas", "United States", "Las Vegas"),
    ("vegas", "United States", "Las Vegas"),
    ("silverstone", "United Kingdom", "Silverstone"),
    ("yas marina", "United Arab Emirates", "Yas Island"),
    ("yas island", "United Arab Emirates", "Yas Island"),
]

CSV_RACE_KEYWORDS = {
    ("Australia", None): "Australian",
    ("Austria", None): "Austrian",
    ("Azerbaijan", None): "Azerbaijan",
    ("Bahrain", None): "Bahrain",
    ("Belgium", None): "Belgian",
    ("Brazil", None): "Brazilian",
    ("Canada", None): "Canadian",
    ("China", None): "Chinese",
    ("France", None): "French",
    ("Germany", None): "German",
    ("Hungary", None): "Hungarian",
    ("Italy", "Imola"): "Emilia Romagna",
    ("Italy", "Monza"): "Italian",
    ("Japan", None): "Japanese",
    ("Mexico", None): "Mexican",
    ("Monaco", None): "Monaco",
    ("Netherlands", None): "Dutch",
    ("Qatar", None): "Qatar",
    ("Saudi Arabia", None): "Saudi",
    ("Singapore", None): "Singapore",
    ("Spain", None): "Spanish",
    ("United Arab Emirates", None): "Abu Dhabi",
    ("United Kingdom", None): "British",
    ("United Kingdom", "Silverstone"): "British",
    ("United States", "Miami"): "Miami",
    ("United States", "Austin"): "United States Grand Prix",
    ("United States", "Las Vegas"): "Las Vegas",
    # Legacy extractor strings
    ("Great Britain", None): "British",
    ("Abu Dhabi", None): "Abu Dhabi",
}


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", text.lower())
    cleaned = cleaned.replace("-", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _alias_in_text(alias: str, text: str) -> bool:
    alias_n = _normalize(alias)
    if not alias_n:
        return False
    if " " in alias_n:
        return alias_n in text
    return re.search(rf"\b{re.escape(alias_n)}\b", text) is not None


def multi_gp_clarification(country: str) -> str:
    races = MULTI_GP_COUNTRIES[country]
    lines = "\n".join(f"- {name} ({location})" for name, location in races)
    return (
        f"Which Grand Prix do you mean? {country} hosts more than one race:\n"
        f"{lines}\n"
        "Please specify the race or circuit."
    )


def csv_race_keyword(country: str | None, location: str | None = None) -> str | None:
    if not country:
        return None
    if location and (country, location) in CSV_RACE_KEYWORDS:
        return CSV_RACE_KEYWORDS[(country, location)]
    return CSV_RACE_KEYWORDS.get((country, None), country)


def resolve_venue(
    country: str | None = None,
    location: str | None = None,
    query: str = "",
) -> dict:
    """Resolve a user/extractor venue to OpenF1 country_name + location.

    Returns:
      {"kind": "ok", "country": str, "location": str | None}
      {"kind": "clarify", "message": str}
      {"kind": "none"}
    """
    parts = [query or "", country or "", location or ""]
    text = _normalize(" ".join(parts))

    specific: tuple[str, str | None] | None = None
    for alias, mapped_country, mapped_location in sorted(GP_ALIASES, key=lambda row: len(row[0]), reverse=True):
        if _alias_in_text(alias, text):
            specific = (mapped_country, mapped_location)
            break

    if specific:
        return {"kind": "ok", "country": specific[0], "location": specific[1]}

    canonical = None
    for candidate in (location, country):
        if not candidate:
            continue
        key = _normalize(candidate)
        if candidate in CANONICAL_COUNTRIES:
            canonical = candidate
            break
        if key in COUNTRY_SYNONYMS:
            canonical = COUNTRY_SYNONYMS[key]
            break

    if canonical is None and text:
        for alias, mapped in sorted(COUNTRY_SYNONYMS.items(), key=lambda item: len(item[0]), reverse=True):
            if _alias_in_text(alias, text):
                canonical = mapped
                break

    if canonical is None:
        if country:
            return {"kind": "ok", "country": country, "location": location or None}
        return {"kind": "none"}

    if canonical in MULTI_GP_COUNTRIES:
        return {"kind": "clarify", "message": multi_gp_clarification(canonical)}

    return {"kind": "ok", "country": canonical, "location": None}
