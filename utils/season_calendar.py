"""Season calendars from historical CSVs, with OpenF1 fallback for unpublished years."""

from __future__ import annotations

from datetime import datetime, timedelta

from utils.f1_api import fetch_year_meetings
from utils.historical_db import circuits_df, csv_available, races_df


def list_calendar_years() -> list[int]:
    years = {datetime.now().year}
    if csv_available() and races_df is not None:
        years.update(int(year) for year in races_df["year"].dropna().unique())
    return sorted(years, reverse=True)


def _iso_date(value) -> str:
    text = str(value or "").strip()
    if not text or text in ("\\N", "nan", "NaT", "None"):
        return ""
    return text[:10]


def _add_days(iso: str, days: int) -> str:
    if not iso:
        return ""
    try:
        return (datetime.strptime(iso, "%Y-%m-%d") + timedelta(days=days)).date().isoformat()
    except ValueError:
        return iso


def _weekend(start: str, end: str) -> tuple[str, str]:
    race_end = _iso_date(end)
    race_start = _iso_date(start)
    if race_end and not race_start:
        race_start = _add_days(race_end, -2)
    if race_start and not race_end:
        race_end = _add_days(race_start, 2)
    return race_start, race_end


def csv_season_calendar(year: int) -> list[dict]:
    if not csv_available() or races_df is None or circuits_df is None:
        return []
    merged = races_df.merge(
        circuits_df[["circuitId", "name", "location", "country"]],
        on="circuitId",
        how="left",
        suffixes=("_race", "_circuit"),
    )
    rows = merged[merged["year"] == year].sort_values("round")
    races = []
    for _, row in rows.iterrows():
        weekend_start, weekend_end = _weekend(row.get("fp1_date"), row.get("date"))
        races.append(
            {
                "round": int(row["round"]),
                "name": row.get("name_race") or row.get("name") or "",
                "date": _iso_date(row.get("date")),
                "weekend_start": weekend_start,
                "weekend_end": weekend_end,
                "circuit": row.get("name_circuit") or "",
                "location": row.get("location") or "",
                "country": row.get("country") or "",
            }
        )
    return races


def get_season_calendar(year: int) -> dict:
    races = csv_season_calendar(year)
    source = "csv"
    if not races:
        races = fetch_year_meetings(year)
        source = "openf1"
    return {
        "year": year,
        "source": source if races else None,
        "races": races,
    }
