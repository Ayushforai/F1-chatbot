"""Detect whether a Grand Prix has been held yet (CSV schedule + OpenF1)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from utils.f1_api import SESSION_NOT_HELD_MESSAGE, _parse_iso, fetch_race_session
from utils.historical_db import _races_for_venue, csv_available

RACE_NOT_HELD_RESULTS_MESSAGE = (
    "The race has not happened yet, so I can't show its results."
)


def _parse_race_date(value) -> date | None:
    text = str(value or "").strip()
    if not text or text in ("\\N", "nan", "NaT", "None"):
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _race_date_from_csv(year: int, country: str, location: str | None) -> date | None:
    if not csv_available():
        return None
    races_yr = _races_for_venue(year, country, location=location)
    if races_yr.empty:
        return None
    return _parse_race_date(races_yr.iloc[0].get("date"))


def _race_start_from_openf1(
    year: int,
    country: str,
    location: str | None,
    now: datetime,
) -> datetime | None | str:
    session = fetch_race_session(year, country, location=location, now=now)
    if isinstance(session, str):
        return session
    return _parse_iso(session.get("date_start"))


def is_future_race(
    year: int,
    country: str,
    location: str | None = None,
    now: datetime | None = None,
) -> bool:
    """True when the scheduled Race session is still in the future."""
    now = now or datetime.now(timezone.utc)
    today = now.date()

    csv_date = _race_date_from_csv(year, country, location)
    if csv_date is not None:
        return csv_date > today

    openf1 = _race_start_from_openf1(year, country, location, now)
    if isinstance(openf1, str):
        return openf1 == SESSION_NOT_HELD_MESSAGE
    if isinstance(openf1, datetime):
        return openf1 > now

    return year > now.year


def race_results_unavailable_reason(
    year: int,
    country: str,
    location: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Return a user-facing message when results cannot exist yet, else None."""
    if is_future_race(year, country, location=location, now=now):
        return RACE_NOT_HELD_RESULTS_MESSAGE
    return None
