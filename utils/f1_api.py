from datetime import datetime, timedelta, timezone

import requests

from utils.venues import MULTI_GP_COUNTRIES, multi_gp_clarification

BASE_URL = "https://api.openf1.org/v1"

# OpenF1 treats data as live from 30 minutes before a session starts until 30 minutes after it ends.
LIVE_WINDOW_PADDING = timedelta(minutes=30)
LIVE_DATA_UNAVAILABLE_MESSAGE = (
    "This bot cannot print live F1 data as there is no live session going currently."
)
SESSION_NOT_HELD_MESSAGE = "The session is yet to be conducted."

def format_lap_time(seconds):
    """Converts raw seconds into a standard F1 MM:SS.ms format."""
    if not seconds:
        return "N/A"
    try:
        sec_float = float(seconds)
        if sec_float >= 60:
            minutes = int(sec_float // 60)
            remaining = sec_float % 60
            return f"{minutes}:{remaining:06.3f}"
        return f"{sec_float:.3f}"
    except (ValueError, TypeError):
        return str(seconds)


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def session_is_live(session: dict, now: datetime | None = None) -> bool:
    """True when `now` falls in OpenF1's live window for this session."""
    now = now or datetime.now(timezone.utc)
    start = _parse_iso(session.get("date_start"))
    end = _parse_iso(session.get("date_end"))
    if start is None or end is None:
        return False
    return (start - LIVE_WINDOW_PADDING) <= now <= (end + LIVE_WINDOW_PADDING)


def get_driver_telemetry(driver_number: int, now: datetime | None = None):
    """Fetch live speed, RPM, and gear from OpenF1 when a session is actually live.

    Does not fall back to an archive snapshot. If no live session (or the API
    cannot serve live car data), returns LIVE_DATA_UNAVAILABLE_MESSAGE.
    """
    try:
        session_res = requests.get(f"{BASE_URL}/sessions?session_key=latest")
        if session_res.status_code != 200:
            return LIVE_DATA_UNAVAILABLE_MESSAGE

        sessions = session_res.json()
        if not sessions:
            return LIVE_DATA_UNAVAILABLE_MESSAGE

        latest_session = sessions[-1] if isinstance(sessions, list) else sessions
        if not session_is_live(latest_session, now=now):
            return LIVE_DATA_UNAVAILABLE_MESSAGE

        car_res = requests.get(
            f"{BASE_URL}/car_data?driver_number={driver_number}&session_key=latest"
        )
        if car_res.status_code != 200:
            return LIVE_DATA_UNAVAILABLE_MESSAGE

        data = car_res.json()
        if not data:
            return LIVE_DATA_UNAVAILABLE_MESSAGE

        latest_metrics = data[-1]
        return {
            "driver_number": driver_number,
            "speed": latest_metrics.get("speed"),
            "rpm": latest_metrics.get("rpm"),
            "gear": latest_metrics.get("gear"),
            "drs": latest_metrics.get("drs"),
            "date": latest_metrics.get("date"),
        }
    except Exception:
        return LIVE_DATA_UNAVAILABLE_MESSAGE


def _payload_list(payload) -> list:
    return payload if isinstance(payload, list) else []


def fetch_session(
    year: int,
    country: str,
    session_name: str = "Race",
    location: str | None = None,
    now: datetime | None = None,
):
    """Return the OpenF1 session dict for a Grand Prix weekend, or an error string."""
    now = now or datetime.now(timezone.utc)
    try:
        res = requests.get(
            f"{BASE_URL}/sessions",
            params={"country_name": country, "year": year, "session_name": session_name},
        )
    except Exception as e:
        return f"Historical Archive Error: {str(e)}"

    if res.status_code == 429:
        return "OpenF1 rate limit exceeded. Please try again in a minute."

    sessions = _payload_list(res.json()) if res.status_code == 200 else []

    if location:
        loc = location.lower()
        sessions = [
            session
            for session in sessions
            if loc in str(session.get("location") or "").lower()
            or loc in str(session.get("circuit_short_name") or "").lower()
        ]

    if not sessions:
        if year >= now.year:
            return SESSION_NOT_HELD_MESSAGE
        label = location or country
        return f"Database Error: Could not locate a {session_name} session in {label} for {year}."

    if len(sessions) > 1 and not location and country in MULTI_GP_COUNTRIES:
        return multi_gp_clarification(country)

    session = sessions[0]
    start = _parse_iso(session.get("date_start"))
    if start and start > now:
        return SESSION_NOT_HELD_MESSAGE
    return session


def fetch_race_session(
    year: int,
    country: str,
    location: str | None = None,
    now: datetime | None = None,
):
    """Return the OpenF1 Race session dict, or an error string."""
    return fetch_session(year, country, session_name="Race", location=location, now=now)


def get_session_info(country: str, year: int = 2024, location: str | None = None):
    """Fetch scheduling data for a Grand Prix race session."""
    session = fetch_race_session(year, country, location=location)
    if isinstance(session, str):
        return session
    return {
        "circuit": session.get("circuit_short_name"),
        "date_start": session.get("date_start"),
        "session_name": session.get("session_name"),
    }


def get_fastest_lap_of_race(
    year: int,
    country: str,
    driver_number: int = None,
    location: str | None = None,
    now: datetime | None = None,
):
    """
    Finds the fastest lap of a specific historical race session.
    If a driver_number is provided, finds THAT driver's specific fastest lap.
    """
    try:
        session = fetch_race_session(year, country, location=location, now=now)
        if isinstance(session, str):
            return session

        session_key = session["session_key"]
        race_label = f"{session.get('location') or country} {year}"

        laps_res = requests.get(f"{BASE_URL}/laps", params={"session_key": session_key})
        laps_data = _payload_list(laps_res.json()) if laps_res.status_code == 200 else []

        if not laps_data:
            return "No lap data found for this session."

        valid_laps = [lap for lap in laps_data if lap.get("lap_duration") is not None]

        if driver_number is not None:
            valid_laps = [lap for lap in valid_laps if lap.get("driver_number") == driver_number]

        if not valid_laps:
            return f"No valid lap data found for Driver {driver_number} in this session."

        fastest_lap = min(valid_laps, key=lambda x: x["lap_duration"])

        driver_res = requests.get(
            f"{BASE_URL}/drivers",
            params={"session_key": session_key, "driver_number": fastest_lap["driver_number"]},
        )
        driver_payload = _payload_list(driver_res.json()) if driver_res.status_code == 200 else []
        driver_name = driver_payload[0]["full_name"] if driver_payload else f"Driver {fastest_lap['driver_number']}"

        return {
            "race": race_label,
            "driver": driver_name,
            "lap_number": fastest_lap["lap_number"],
            "lap_time": format_lap_time(fastest_lap["lap_duration"]),
            "lap_time_seconds": fastest_lap["lap_duration"],
            "average_speed": fastest_lap.get("st_speed"),
        }

    except Exception as e:
        return f"Historical Archive Error: {str(e)}"


def get_historical_lap(
    year: int,
    country: str,
    driver_number: int,
    lap_number: int,
    location: str | None = None,
    now: datetime | None = None,
):
    """Fetch data for a specific lap of a specific driver in a historical race."""
    try:
        session = fetch_race_session(year, country, location=location, now=now)
        if isinstance(session, str):
            return session

        session_key = session["session_key"]
        race_label = f"{session.get('location') or country} {year}"

        laps_res = requests.get(
            f"{BASE_URL}/laps",
            params={
                "session_key": session_key,
                "driver_number": driver_number,
                "lap_number": lap_number,
            },
        )
        laps_data = _payload_list(laps_res.json()) if laps_res.status_code == 200 else []

        if not laps_data:
            return f"No data found for Driver {driver_number}, Lap {lap_number} in {race_label}."

        lap = laps_data[0]

        driver_res = requests.get(
            f"{BASE_URL}/drivers",
            params={"session_key": session_key, "driver_number": driver_number},
        )
        driver_payload = _payload_list(driver_res.json()) if driver_res.status_code == 200 else []
        driver_name = driver_payload[0]["full_name"] if driver_payload else f"Driver {driver_number}"

        return {
            "race": race_label,
            "driver": driver_name,
            "lap_number": lap["lap_number"],
            "lap_time": format_lap_time(lap.get("lap_duration")),
            "lap_time_seconds": lap.get("lap_duration"),
            "base_speed": lap.get("st_speed"),
            "is_pit_out_lap": lap.get("is_pit_out_lap"),
        }

    except Exception as e:
        return f"Historical Archive Error: {str(e)}"


def _lap_peak_speed_kmh(lap: dict) -> tuple[float | None, str | None]:
    """Return the best speed-trap reading on a lap and which field it came from."""
    best = None
    best_field = None
    for field in ("st_speed", "i1_speed", "i2_speed"):
        value = lap.get(field)
        if value is None:
            continue
        try:
            speed = float(value)
        except (TypeError, ValueError):
            continue
        if speed <= 0:
            continue
        if best is None or speed > best:
            best = speed
            best_field = field
    return best, best_field


def _max_trap_from_session(
    session: dict,
    *,
    driver_number: int | None = None,
    session_name: str,
) -> dict | None:
    session_key = session["session_key"]
    race_label = (
        f"{session.get('location') or session.get('circuit_short_name')} "
        f"{session.get('year')} ({session_name})"
    )

    params: dict = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number

    laps_res = requests.get(f"{BASE_URL}/laps", params=params)
    laps_data = _payload_list(laps_res.json()) if laps_res.status_code == 200 else []
    if not laps_data:
        return None

    best_lap = None
    best_speed = None
    best_field = None
    for lap in laps_data:
        if lap.get("is_pit_out_lap"):
            continue
        speed, field = _lap_peak_speed_kmh(lap)
        if speed is None:
            continue
        if best_speed is None or speed > best_speed:
            best_speed = speed
            best_field = field
            best_lap = lap

    if best_lap is None or best_speed is None:
        return None

    driver_res = requests.get(
        f"{BASE_URL}/drivers",
        params={
            "session_key": session_key,
            "driver_number": best_lap["driver_number"],
        },
    )
    driver_payload = _payload_list(driver_res.json()) if driver_res.status_code == 200 else []
    driver_name = (
        driver_payload[0]["full_name"]
        if driver_payload
        else f"Driver {best_lap['driver_number']}"
    )

    field_labels = {
        "st_speed": "speed trap",
        "i1_speed": "intermediate 1",
        "i2_speed": "intermediate 2",
    }

    return {
        "race": race_label,
        "measurement": "OpenF1 speed trap",
        "speed_kmh": best_speed,
        "speed_field": best_field,
        "speed_field_label": field_labels.get(best_field, best_field),
        "driver": driver_name,
        "driver_number": best_lap["driver_number"],
        "lap_number": best_lap["lap_number"],
        "session": session_name,
    }


def _fetch_sessions_for_year(
    year: int,
    session_name: str,
    now: datetime | None = None,
) -> list[dict] | str:
    """Return completed OpenF1 sessions for a calendar year, or an error string."""
    now = now or datetime.now(timezone.utc)
    try:
        res = requests.get(
            f"{BASE_URL}/sessions",
            params={"year": year, "session_name": session_name},
        )
    except Exception as e:
        return f"Historical Archive Error: {str(e)}"

    if res.status_code == 429:
        return "OpenF1 rate limit exceeded. Please try again in a minute."

    sessions = _payload_list(res.json()) if res.status_code == 200 else []
    completed: list[dict] = []
    for session in sessions:
        start = _parse_iso(session.get("date_start"))
        if start and start > now:
            continue
        completed.append(session)

    if not completed:
        if year >= now.year:
            return SESSION_NOT_HELD_MESSAGE
        return f"No {session_name} sessions found for {year}."

    return completed


def get_max_speed_trap_season(
    year: int,
    driver_number: int | None = None,
    now: datetime | None = None,
):
    """Return the highest speed-trap reading across an entire OpenF1 season."""
    if year < 2023:
        return "OpenF1 speed-trap data is only available from 2023 onward."

    try:
        best_packet = None
        for session_name in ("Qualifying", "Race"):
            sessions = _fetch_sessions_for_year(year, session_name, now=now)
            if isinstance(sessions, str):
                continue
            for session in sessions:
                packet = _max_trap_from_session(
                    session,
                    driver_number=driver_number,
                    session_name=session_name,
                )
                if packet is None:
                    continue
                if best_packet is None or packet["speed_kmh"] > best_packet["speed_kmh"]:
                    best_packet = packet

        if best_packet is None:
            return f"No speed-trap readings found for the {year} season."

        return best_packet

    except Exception as e:
        return f"Historical Archive Error: {str(e)}"


def get_max_speed_trap(
    year: int,
    country: str,
    location: str | None = None,
    driver_number: int | None = None,
    now: datetime | None = None,
):
    """Return the highest speed-trap reading from OpenF1 qualifying or race."""
    try:
        best_packet = None
        for session_name in ("Qualifying", "Race"):
            session = fetch_session(
                year,
                country,
                session_name=session_name,
                location=location,
                now=now,
            )
            if isinstance(session, str):
                continue
            packet = _max_trap_from_session(
                session,
                driver_number=driver_number,
                session_name=session_name,
            )
            if packet is None:
                continue
            if best_packet is None or packet["speed_kmh"] > best_packet["speed_kmh"]:
                best_packet = packet

        if best_packet is None:
            session = fetch_session(year, country, session_name="Race", location=location, now=now)
            if isinstance(session, str):
                return session
            return "No speed-trap readings found for this Grand Prix."

        return best_packet

    except Exception as e:
        return f"Historical Archive Error: {str(e)}"


def fetch_year_meetings(year: int) -> list[dict]:
    """Return OpenF1 meetings for a season, oldest round first."""
    try:
        res = requests.get(
            f"{BASE_URL}/meetings",
            params={"year": year},
            timeout=12,
        )
    except requests.RequestException:
        return []
    if res.status_code != 200:
        return []
    meetings = _payload_list(res.json())
    meetings.sort(key=lambda row: str(row.get("date_start") or ""))
    races = []
    for index, meeting in enumerate(meetings, start=1):
        date = str(meeting.get("date_start") or "")[:10]
        weekend_end = date
        try:
            weekend_end = (
                datetime.strptime(date, "%Y-%m-%d") + timedelta(days=2)
            ).date().isoformat()
        except ValueError:
            pass
        races.append(
            {
                "round": index,
                "name": meeting.get("meeting_name") or meeting.get("circuit_short_name") or "Grand Prix",
                "date": date,
                "weekend_start": date,
                "weekend_end": weekend_end,
                "circuit": meeting.get("circuit_short_name") or "",
                "location": meeting.get("location") or "",
                "country": meeting.get("country_name") or "",
            }
        )
    return races


def get_openf1_session_classification(
    year: int,
    country: str,
    session_name: str,
    location: str | None = None,
    now: datetime | None = None,
) -> dict | str:
    """Return session classification from OpenF1 session_result rows."""
    session = fetch_session(
        year,
        country,
        session_name=session_name,
        location=location,
        now=now,
    )
    if isinstance(session, str):
        return session

    session_key = session["session_key"]
    try:
        res = requests.get(
            f"{BASE_URL}/session_result",
            params={"session_key": session_key},
            timeout=12,
        )
        results = _payload_list(res.json()) if res.status_code == 200 else []
        if not results:
            return f"No {session_name} results found for this session."

        drivers_res = requests.get(
            f"{BASE_URL}/drivers",
            params={"session_key": session_key},
            timeout=12,
        )
        drivers = {
            row["driver_number"]: row
            for row in _payload_list(drivers_res.json())
        }
    except Exception as e:
        return f"Historical Archive Error: {str(e)}"

    meeting_name = session.get("meeting_name") or session.get("circuit_short_name") or "Grand Prix"
    rows = sorted(results, key=lambda row: row.get("position") or 999)

    if session_name == "Qualifying":
        grid = []
        for row in rows:
            driver = drivers.get(row.get("driver_number"), {})
            duration = row.get("duration")
            grid.append(
                {
                    "Position": row.get("position"),
                    "Driver": driver.get("full_name") or f"Driver {row.get('driver_number')}",
                    "Team": driver.get("team_name") or "N/A",
                    "Q1": format_lap_time(duration) if duration else "N/A",
                    "Q2": "N/A",
                    "Q3": "N/A",
                }
            )
        return {
            "Year": year,
            "Grand Prix": meeting_name,
            "Session": "Qualifying",
            "Grid": grid,
        }

    finishers = []
    for row in rows:
        driver = drivers.get(row.get("driver_number"), {})
        gap = row.get("gap_to_leader")
        duration = row.get("duration")
        if row.get("position") == 1:
            time_value = format_lap_time(duration) if duration is not None else "N/A"
        else:
            time_value = format_lap_time(gap if gap is not None else duration)
        finishers.append(
            {
                "Position": str(row.get("position") or "?"),
                "Driver": driver.get("full_name") or f"Driver {row.get('driver_number')}",
                "Team": driver.get("team_name") or "N/A",
                "Gap / Race Time": time_value,
                "Status": "DNF" if row.get("dnf") else "Finished",
                "Fastest Lap": "N/A",
                "Fastest Lap Number": "N/A",
                "Points": 0,
            }
        )
    return {
        "Year": year,
        "Grand Prix": meeting_name,
        "Session": session_name,
        "Classification": finishers,
    }
