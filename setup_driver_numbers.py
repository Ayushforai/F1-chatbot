"""Fetch current-grid driver numbers from OpenF1 and write data/driver_numbers.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.openf1.org/v1"
OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "driver_numbers.json"


def _fetch_json(url: str, params: dict | None = None) -> list | dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    return [payload] if payload else []


def _latest_race_session_key(year: int) -> int | None:
    sessions = _fetch_json(
        f"{BASE_URL}/sessions",
        {"year": year, "session_type": "Race"},
    )
    if not sessions:
        return None
    sessions.sort(key=lambda row: row.get("date_start") or "")
    return sessions[-1]["session_key"]


def _aliases_for_driver(row: dict) -> list[str]:
    aliases: set[str] = set()
    for key in ("first_name", "last_name", "full_name", "name_acronym", "broadcast_name"):
        value = row.get(key)
        if not value:
            continue
        aliases.add(str(value).lower())
        for part in str(value).replace(".", " ").split():
            if len(part) >= 2:
                aliases.add(part.lower())
    return sorted(aliases)


def fetch_season_drivers(year: int) -> list[dict]:
    session_key = _latest_race_session_key(year)
    if session_key is None:
        return []

    rows = _fetch_json(f"{BASE_URL}/drivers", {"session_key": session_key})
    drivers: list[dict] = []
    for row in sorted(rows, key=lambda item: item.get("driver_number") or 0):
        drivers.append(
            {
                "driver_number": row["driver_number"],
                "full_name": row.get("full_name"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "name_acronym": row.get("name_acronym"),
                "broadcast_name": row.get("broadcast_name"),
                "team_name": row.get("team_name"),
                "aliases": _aliases_for_driver(row),
            }
        )
    return drivers


def build_driver_numbers_document(years: list[int]) -> dict:
    seasons: dict[str, dict] = {}
    for year in sorted(set(years)):
        drivers = fetch_season_drivers(year)
        if not drivers:
            print(f"  [skip] No OpenF1 driver data for {year}")
            continue
        seasons[str(year)] = {
            "session_key": _latest_race_session_key(year),
            "driver_count": len(drivers),
            "drivers": drivers,
        }
        print(f"  [ok] {year}: {len(drivers)} drivers")

    if not seasons:
        raise RuntimeError("No driver data fetched from OpenF1.")

    latest_year = max(int(y) for y in seasons)
    return {
        "source": "OpenF1 API (https://api.openf1.org/v1/drivers)",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "default_season": latest_year,
        "seasons": seasons,
    }


def write_driver_numbers_document(document: dict, output_path: Path = OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[datetime.now().year - 1, datetime.now().year],
        help="Season years to fetch (default: previous and current calendar year)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"Output JSON path (default: {OUTPUT_PATH})",
    )
    args = parser.parse_args()

    print(f"Fetching driver numbers from OpenF1 for: {', '.join(map(str, args.years))}")
    document = build_driver_numbers_document(args.years)
    path = write_driver_numbers_document(document, args.output)
    print(f"Wrote {path} ({document['default_season']} default season, "
          f"{len(document['seasons'])} seasons)")


if __name__ == "__main__":
    main()
