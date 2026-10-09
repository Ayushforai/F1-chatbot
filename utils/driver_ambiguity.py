"""Surname disambiguation: current-grid default + optional data/driver_ambiguity.json overrides."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from utils.driver_names import (
    _catalog_entry,
    _load_catalog,
    _normalize,
    _surname,
)

OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "driver_ambiguity.json"


def _identity_haystack(ref: str | None, query: str) -> str:
    return _normalize(f"{ref or ''} {query or ''}")


def forename_token(full_name: str) -> str:
    parts = (full_name or "").split()
    return parts[0].lower() if parts else ""


def mentions_driver_forename(full_name: str, *, ref: str | None = None, query: str = "") -> bool:
    token = forename_token(full_name)
    if not token:
        return False
    haystack = _identity_haystack(ref, query)
    return bool(re.search(rf"\b{re.escape(token)}\b", haystack))


def grid_season_for_ambiguity(year: int | None) -> int | None:
    """Season whose OpenF1 grid may bias surname defaults (never guess a random fallback year)."""
    from utils.driver_numbers import available_seasons, default_season

    seasons = set(available_seasons())
    if year is not None:
        return year if year in seasons else None
    default = default_season()
    return default if default in seasons else None


def _catalog_entries_for_surname(surname: str) -> list[dict]:
    rows, _ = _load_catalog()
    needle = _normalize(surname)
    return [entry for entry in rows if _normalize(entry.get("surname") or "") == needle]


@lru_cache(maxsize=1)
def _load_override_groups() -> list[dict]:
    if not OVERRIDES_PATH.is_file():
        return []
    try:
        payload = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(payload.get("groups") or [])


def _override_group(surname: str) -> dict | None:
    needle = _normalize(surname)
    for group in _load_override_groups():
        if _normalize(group.get("surname") or "") == needle:
            return group
    return None


def _grid_catalog_entry(surname: str, year: int | None) -> dict | None:
    season = grid_season_for_ambiguity(year)
    if season is None:
        return None

    from utils.driver_numbers import _driver_rows

    for row in _driver_rows(season):
        if _normalize(row.get("last_name") or "") != _normalize(surname):
            continue
        first = (row.get("first_name") or "").strip()
        last = (row.get("last_name") or "").strip()
        if not first or not last:
            continue
        full_name = f"{first} {last}"
        entry = _catalog_entry(full_name)
        if entry:
            return entry
        return {
            "full_name": full_name,
            "surname": _surname(full_name),
            "active": True,
            "seasons": [],
            "aliases": [],
        }
    return None


def _legacy_from_override(group: dict, haystack: str) -> dict | None:
    for legacy in group.get("legacy") or []:
        full_name = (legacy.get("full_name") or "").strip()
        if not full_name:
            continue
        tokens = legacy.get("tokens") or [forename_token(full_name)]
        for token in tokens:
            token_norm = _normalize(str(token))
            if token_norm and re.search(rf"\b{re.escape(token_norm)}\b", haystack):
                return _catalog_entry(full_name) or {"full_name": full_name, "surname": _surname(full_name)}
    return None


def apply_surname_ambiguity_policy(
    entry: dict | None,
    *,
    ref: str | None = None,
    query: str = "",
    year: int | None = None,
) -> dict | None:
    """
    When several drivers share a surname, prefer the current-season grid driver unless
    the user names a legacy driver (forename in query/ref, or tokens in driver_ambiguity.json).
    """
    if not entry:
        return entry

    surname = entry.get("surname") or _surname(entry.get("full_name") or "")
    collisions = _catalog_entries_for_surname(surname)
    if len(collisions) < 2:
        return entry

    haystack = _identity_haystack(ref, query)
    override = _override_group(surname)
    if override:
        legacy = _legacy_from_override(override, haystack)
        if legacy:
            return legacy
        default_name = (override.get("default") or override.get("default_season_driver") or "").strip()
        if default_name:
            return _catalog_entry(default_name) or entry

    for other in collisions:
        if mentions_driver_forename(other["full_name"], ref=ref, query=query):
            return other

    grid_entry = _grid_catalog_entry(surname, year)
    if grid_entry:
        return grid_entry

    return entry


# Backwards-compatible helpers used in tests and historical_db
def mentions_jos_verstappen(*, ref: str | None = None, query: str = "") -> bool:
    return mentions_driver_forename("Jos Verstappen", ref=ref, query=query)


def mentions_max_verstappen(*, ref: str | None = None, query: str = "") -> bool:
    return mentions_driver_forename("Max Verstappen", ref=ref, query=query)


def apply_verstappen_policy(
    entry: dict | None,
    *,
    ref: str | None = None,
    query: str = "",
    year: int | None = None,
) -> dict | None:
    return apply_surname_ambiguity_policy(entry, ref=ref, query=query, year=year)


def preferred_ergast_driver_ref(
    driver_ref: str,
    *,
    query: str = "",
    year: int | None = None,
) -> str | None:
    """Map a bare surname slug to the preferred Ergast driverRef when ambiguous."""
    from utils.driver_names import resolve_driver_identity

    identity = resolve_driver_identity(ref=driver_ref, query=query or driver_ref, year=year)
    if not identity:
        return None
    full_name = identity["full_name"]
    try:
        from utils.historical_db import drivers_df

        if drivers_df is None:
            return None
        parts = full_name.split()
        if len(parts) < 2:
            return None
        forename, surname = parts[0], parts[-1]
        match = drivers_df[
            (drivers_df["forename"].str.lower() == forename.lower())
            & (drivers_df["surname"].str.lower() == surname.lower())
        ]
        if match.empty:
            return None
        return str(match.iloc[0]["driverRef"]).lower()
    except Exception:
        return None
