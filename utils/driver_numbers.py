"""Resolve driver names and car numbers using OpenF1 grid + F1DriversDataset names."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from utils.driver_names import resolve_driver_identity

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "driver_numbers.json"

_CAR_NUMBER_RE = re.compile(r"(?:#|driver\s+)(?P<number>\d{1,2})\b", re.I)


@lru_cache(maxsize=1)
def _load_document() -> dict | None:
    if not DATA_PATH.is_file():
        return None
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def available_seasons() -> list[int]:
    document = _load_document()
    if not document:
        return []
    return sorted(int(year) for year in document.get("seasons", {}))


def default_season() -> int | None:
    document = _load_document()
    if not document:
        return None
    value = document.get("default_season")
    return int(value) if value is not None else None


def _season_key(year: int | None) -> str | None:
    document = _load_document()
    if not document:
        return None
    seasons = document.get("seasons") or {}
    if year is not None and str(year) in seasons:
        return str(year)
    default = document.get("default_season")
    if default is not None and str(default) in seasons:
        return str(default)
    if seasons:
        return max(seasons.keys(), key=int)
    return None


def _normalize_ref(value: str | int | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9\u00C0-\u024F\-'\s]", " ", text)
    return " ".join(text.split())


def _driver_rows(year: int | None = None) -> list[dict]:
    document = _load_document()
    if not document:
        return []
    season = _season_key(year)
    if season is None:
        return []
    return list((document.get("seasons") or {}).get(season, {}).get("drivers") or [])


def resolve_driver_number(ref: str | int | None, *, year: int | None = None) -> int | None:
    """Map a driver surname, first name, acronym, or #car number to OpenF1 driver_number."""
    if ref is None or ref == "":
        return None

    if isinstance(ref, int):
        return ref

    text = str(ref).strip()
    if text.isdigit():
        return int(text)

    car_match = _CAR_NUMBER_RE.search(text)
    if car_match:
        return int(car_match.group("number"))

    needle = _normalize_ref(text)
    if not needle:
        return None

    for row in _driver_rows(year):
        number = row.get("driver_number")
        if number is not None and needle == str(number):
            return int(number)

        candidates = {_normalize_ref(row.get("last_name")), _normalize_ref(row.get("first_name"))}
        candidates.discard("")
        if needle in candidates:
            return int(number)

        for alias in row.get("aliases") or []:
            alias_norm = _normalize_ref(alias)
            if needle == alias_norm or needle in alias_norm.split():
                return int(number)

        full_name = _normalize_ref(row.get("full_name"))
        if needle and (needle in full_name or full_name.endswith(needle)):
            return int(number)

    return None


def resolve_driver_from_query(query: str, *, year: int | None = None) -> int | None:
    """Best-effort driver_number parse from free text (#44, 'Verstappen', etc.)."""
    if not query:
        return None

    car_match = _CAR_NUMBER_RE.search(query)
    if car_match:
        return int(car_match.group("number"))

    rows = _driver_rows(year)
    if not rows:
        return None

    q_lower = query.lower()
    matches: list[tuple[int, int]] = []

    for row in rows:
        number = row.get("driver_number")
        if number is None:
            continue
        for alias in row.get("aliases") or []:
            alias_norm = _normalize_ref(alias)
            if len(alias_norm) < 3:
                continue
            if re.search(rf"\b{re.escape(alias_norm)}\b", q_lower):
                matches.append((len(alias_norm), int(number)))

    if not matches:
        return None

    matches.sort(key=lambda item: item[0], reverse=True)
    best_len = matches[0][0]
    top = [num for length, num in matches if length == best_len]
    if len(set(top)) == 1:
        return top[0]
    return None


def enrich_telemetry_params(params: dict, query: str = "", *, year: int | None = None) -> dict:
    """Fill missing driver_number / driver_name using OpenF1 grid + F1DriversDataset."""
    enriched = dict(params)
    season_year = year if year is not None else enriched.get("year")

    identity = resolve_driver_identity(
        enriched.get("driver_name"),
        query=query,
        year=season_year,
    )
    if identity and not enriched.get("driver_name"):
        enriched["driver_name"] = identity["surname"]

    if enriched.get("driver_number") in (None, ""):
        for candidate in (enriched.get("driver_name"), query):
            if not candidate:
                continue
            resolved = resolve_driver_number(candidate, year=season_year)
            if resolved is None and candidate is query:
                resolved = resolve_driver_from_query(candidate, year=season_year)
            if resolved is not None:
                enriched["driver_number"] = resolved
                break

    if not enriched.get("driver_name") and enriched.get("driver_number") is not None:
        for row in _driver_rows(season_year):
            if row.get("driver_number") == enriched["driver_number"]:
                enriched["driver_name"] = row.get("last_name") or row.get("full_name")
                break

    return enriched
