"""Resolve driver identities from data/historical_csvs/F1DriversDataset.csv."""

from __future__ import annotations

import ast
import csv
import re
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "historical_csvs" / "F1DriversDataset.csv"

_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii"}


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^a-z0-9\u00C0-\u024F\-'\s]", " ", str(text).lower())
    return " ".join(cleaned.split())


def _parse_seasons(raw: str) -> list[int]:
    try:
        values = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    seasons: list[int] = []
    for value in values:
        try:
            seasons.append(int(value))
        except (TypeError, ValueError):
            continue
    return seasons


def _surname(full_name: str) -> str:
    parts = full_name.split()
    if not parts:
        return full_name
    if len(parts) >= 2 and parts[-1].lower().rstrip(".") in {s.rstrip(".") for s in _SUFFIXES}:
        return parts[-2]
    if len(parts) >= 2 and parts[-2].lower() in {"de", "da", "di", "del", "van", "von"}:
        return " ".join(parts[-2:])
    return parts[-1]


def _aliases(full_name: str) -> set[str]:
    aliases = {_normalize(full_name), _normalize(_surname(full_name))}
    parts = full_name.split()
    if len(parts) >= 2:
        aliases.add(_normalize(parts[0]))
        aliases.add(_normalize(f"{parts[0]} {parts[-1]}"))
    return {alias for alias in aliases if alias}


@lru_cache(maxsize=1)
def _load_catalog() -> tuple[list[dict], dict[str, list[int]]]:
    if not DATA_PATH.is_file():
        return [], {}

    rows: list[dict] = []
    alias_index: dict[str, list[int]] = {}

    with DATA_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            full_name = (row.get("Driver") or "").strip()
            if not full_name:
                continue
            seasons = _parse_seasons(row.get("Seasons") or "[]")
            active = str(row.get("Active", "")).strip().lower() in {"true", "1", "yes"}
            entry = {
                "full_name": full_name,
                "surname": _surname(full_name),
                "active": active,
                "seasons": seasons,
                "aliases": sorted(_aliases(full_name)),
            }
            index = len(rows)
            rows.append(entry)
            for alias in entry["aliases"]:
                alias_index.setdefault(alias, []).append(index)

    return rows, alias_index


def catalog_available() -> bool:
    rows, _ = _load_catalog()
    return bool(rows)


def _score_match(entry: dict, *, year: int | None, alias: str, source: str) -> int:
    score = len(alias)
    if source == "full":
        score += 4
    if year is not None and year in entry["seasons"]:
        score += 12
    if entry["active"]:
        score += 6
    if year is None and entry["active"]:
        score += 2
    return score


def _best_match(candidates: list[tuple[int, str, str]], *, year: int | None) -> dict | None:
    if not candidates:
        return None

    rows, _ = _load_catalog()
    scored: list[tuple[int, dict]] = []
    for index, alias, source in candidates:
        entry = rows[index]
        scored.append((_score_match(entry, year=year, alias=alias, source=source), entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    top = [entry for score, entry in scored if score == best_score]
    if len(top) > 1 and year is not None:
        season_matches = [entry for entry in top if year in entry["seasons"]]
        if len(season_matches) == 1:
            return season_matches[0]
    if len(top) > 1:
        active = [entry for entry in top if entry["active"]]
        if len(active) == 1:
            return active[0]
    return top[0]


def match_driver_in_text(text: str, *, year: int | None = None) -> dict | None:
    """Find the best driver catalog match inside free-form query text."""
    rows, alias_index = _load_catalog()
    if not rows or not text:
        return None

    haystack = _normalize(text)
    candidates: list[tuple[int, str, str]] = []

    for alias, indexes in alias_index.items():
        if len(alias) < 3:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", haystack):
            source = "full" if " " in alias else "token"
            for index in indexes:
                candidates.append((index, alias, source))

    return _best_match(candidates, year=year)


def match_driver_ref(ref: str, *, year: int | None = None) -> dict | None:
    """Match a driver surname or full name against the catalog."""
    rows, alias_index = _load_catalog()
    if not rows or not ref:
        return None

    needle = _normalize(ref)
    if not needle:
        return None

    candidates: list[tuple[int, str, str]] = []
    for alias, indexes in alias_index.items():
        if needle == alias or needle in alias.split():
            source = "full" if " " in alias else "token"
            for index in indexes:
                candidates.append((index, alias, source))

    if not candidates:
        return None
    return _best_match(candidates, year=year)


def resolve_driver_identity(
    ref: str | None = None,
    *,
    query: str = "",
    year: int | None = None,
) -> dict | None:
    """Return canonical driver identity from ref and/or query text."""
    for candidate in (ref,):
        if candidate:
            match = match_driver_ref(candidate, year=year)
            if match:
                return match
    if query:
        return match_driver_in_text(query, year=year)
    return None
