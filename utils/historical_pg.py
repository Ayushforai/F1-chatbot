"""PostgreSQL implementations of historical archive lookups (same packets as CSV)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd

from utils.db import connect
from utils.venues import MULTI_GP_COUNTRIES, csv_race_keywords, multi_gp_clarification

CSV_UNAVAILABLE_MESSAGE = (
    "Historical PostgreSQL archive is not available. "
    "Run: python scripts/load_ergast_to_postgres.py"
)


def _cell(value) -> str:
    if value is None or str(value) in ("\\N", "nan", "NaT", "None", ""):
        return "N/A"
    return str(value)


def _name_pattern(year: int, country: str, location: str | None) -> tuple[str, list]:
    if country in MULTI_GP_COUNTRIES and not location:
        keywords: list[str] = []
        for _, mapped_location in MULTI_GP_COUNTRIES[country]:
            keywords.extend(csv_race_keywords(country, mapped_location))
    else:
        keywords = csv_race_keywords(country, location)
    if not keywords:
        return "", []
    pattern = "|".join(re.escape(k) for k in keywords)
    return pattern, [year, pattern]


def races_for_venue_df(year: int, country: str, location: str | None = None) -> pd.DataFrame:
    sql = """
        SELECT race_id AS "raceId", year, round, circuit_id AS "circuitId",
               name, race_date AS date, race_time AS time, url
        FROM f1.races
        WHERE year = %s
    """
    params: list = [year]
    if country:
        pattern, extra = _name_pattern(year, country, location)
        if not pattern:
            return pd.DataFrame()
        sql += " AND name ~* %s"
        params = extra
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return pd.DataFrame(rows)


def archive_available() -> bool:
    try:
        with connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM f1.races").fetchone()
        return bool(row and int(row["n"]) > 0)
    except Exception:
        return False


def _require() -> str | None:
    if archive_available():
        return None
    return CSV_UNAVAILABLE_MESSAGE


def resolve_driver(driver_ref: str) -> tuple[int, str] | None:
    if not driver_ref or not str(driver_ref).strip():
        return None
    ref = str(driver_ref).strip()
    slug = ref.lower().replace(" ", "_")
    with connect() as conn:
        row = conn.execute(
            """
            SELECT driver_id, forename, surname
            FROM f1.drivers
            WHERE lower(driver_ref) = %s
            LIMIT 1
            """,
            (slug,),
        ).fetchone()
        if row:
            return int(row["driver_id"]), f"{row['forename']} {row['surname']}"

        parts = ref.split()
        if len(parts) >= 2:
            forename, surname = parts[0], parts[-1]
            row = conn.execute(
                """
                SELECT driver_id, forename, surname
                FROM f1.drivers
                WHERE forename ILIKE %s AND surname ILIKE %s
                LIMIT 1
                """,
                (f"%{forename}%", f"%{surname}%"),
            ).fetchone()
            if row:
                return int(row["driver_id"]), f"{row['forename']} {row['surname']}"
            row = conn.execute(
                """
                SELECT driver_id, forename, surname
                FROM f1.drivers
                WHERE (forename || ' ' || surname) ILIKE %s
                LIMIT 1
                """,
                (f"%{ref}%",),
            ).fetchone()
            if row:
                return int(row["driver_id"]), f"{row['forename']} {row['surname']}"

        row = conn.execute(
            """
            SELECT driver_id, forename, surname
            FROM f1.drivers
            WHERE surname ILIKE %s
            LIMIT 1
            """,
            (f"%{ref}%",),
        ).fetchone()
        if row:
            return int(row["driver_id"]), f"{row['forename']} {row['surname']}"
        row = conn.execute(
            """
            SELECT driver_id, forename, surname
            FROM f1.drivers
            WHERE forename ILIKE %s
            LIMIT 1
            """,
            (f"%{ref}%",),
        ).fetchone()
        if row:
            return int(row["driver_id"]), f"{row['forename']} {row['surname']}"
    return None


def _resolve_race(year: int, country: str, location: str | None = None) -> tuple[int, str] | str:
    races_yr = races_for_venue_df(year, country, location=location)
    if races_yr.empty:
        return f"No races found for {year}" + (f" matching '{country}'." if country else ".")
    if country in MULTI_GP_COUNTRIES and not location and len(races_yr) > 1:
        return multi_gp_clarification(country)
    row = races_yr.iloc[0]
    return int(row["raceId"]), row["name"]


def _pick_race(
    year: int, country: str, location: str | None
) -> tuple[int, str] | str:
    from utils.race_schedule import (
        RACE_NOT_HELD_RESULTS_MESSAGE,
        _parse_race_date,
        race_results_unavailable_reason,
    )

    missing = _require()
    if missing:
        return missing
    races_yr = races_for_venue_df(year, country, location=location)
    if races_yr.empty:
        unavailable = race_results_unavailable_reason(year, country, location=location)
        if unavailable:
            return unavailable
        return f"No races found for {year}" + (f" matching '{country}'." if country else ".")
    if country in MULTI_GP_COUNTRIES and not location and len(races_yr) > 1:
        return multi_gp_clarification(country)
    race_date = _parse_race_date(races_yr.iloc[0].get("date"))
    if race_date and race_date > datetime.now(timezone.utc).date():
        return RACE_NOT_HELD_RESULTS_MESSAGE
    unavailable = race_results_unavailable_reason(year, country, location=location)
    if unavailable:
        return unavailable
    return int(races_yr.iloc[0]["raceId"]), races_yr.iloc[0]["name"]


def get_race_results(
    year: int, country: str, top_n: int | None = None, location: str | None = None
) -> dict | str:
    picked = _pick_race(year, country, location)
    if not isinstance(picked, tuple):
        return picked
    race_id, race_name = picked
    limit_sql = f"LIMIT {int(top_n)}" if top_n is not None else ""
    sql = f"""
        SELECT res.position_text, res.points, res.race_time, res.fastest_lap_time,
               res.fastest_lap, res.fastest_lap_rank, st.status,
               d.forename, d.surname, c.name AS team
        FROM f1.results res
        JOIN f1.drivers d ON d.driver_id = res.driver_id
        JOIN f1.constructors c ON c.constructor_id = res.constructor_id
        JOIN f1.status st ON st.status_id = res.status_id
        WHERE res.race_id = %s
        ORDER BY res.position_order
        {limit_sql}
    """
    try:
        with connect() as conn:
            rows = conn.execute(sql, (race_id,)).fetchall()
        finishers = []
        overall_fl = None
        for row in rows:
            fl_time = _cell(row.get("fastest_lap_time"))
            entry = {
                "Position": row["position_text"],
                "Driver": f"{row['forename']} {row['surname']}",
                "Team": row["team"],
                "Gap / Race Time": _cell(row.get("race_time")),
                "Status": _cell(row.get("status")),
                "Fastest Lap": fl_time,
                "Fastest Lap Number": _cell(row.get("fastest_lap")),
                "Points": row["points"],
            }
            finishers.append(entry)
            rank = row.get("fastest_lap_rank")
            if rank is not None and int(rank) == 1 and fl_time != "N/A":
                overall_fl = {
                    "Driver": entry["Driver"],
                    "Time": fl_time,
                    "Lap": entry["Fastest Lap Number"],
                }
        packet = {"Year": year, "Grand Prix": race_name, "Classification": finishers}
        if overall_fl:
            packet["Overall Fastest Lap"] = overall_fl
        return packet
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_qualifying_results(year: int, country: str, location: str | None = None) -> dict | str:
    picked = _pick_race(year, country, location)
    if not isinstance(picked, tuple):
        return picked
    race_id, race_name = picked
    try:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT q.position, q.q1, q.q2, q.q3, d.forename, d.surname, c.name AS team
                FROM f1.qualifying q
                JOIN f1.drivers d ON d.driver_id = q.driver_id
                JOIN f1.constructors c ON c.constructor_id = q.constructor_id
                WHERE q.race_id = %s
                ORDER BY q.position
                """,
                (race_id,),
            ).fetchall()
        if not rows:
            return "No qualifying results found for this Grand Prix."
        grid = [
            {
                "Position": int(row["position"]),
                "Driver": f"{row['forename']} {row['surname']}",
                "Team": row["team"],
                "Q1": _cell(row.get("q1")),
                "Q2": _cell(row.get("q2")),
                "Q3": _cell(row.get("q3")),
            }
            for row in rows
        ]
        return {
            "Year": year,
            "Grand Prix": race_name,
            "Session": "Qualifying",
            "Grid": grid,
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_sprint_results(year: int, country: str, location: str | None = None) -> dict | str:
    picked = _pick_race(year, country, location)
    if not isinstance(picked, tuple):
        return picked
    race_id, race_name = picked
    try:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT res.position_text, res.points, res.race_time, res.fastest_lap_time,
                       res.fastest_lap, st.status, d.forename, d.surname, c.name AS team
                FROM f1.sprint_results res
                JOIN f1.drivers d ON d.driver_id = res.driver_id
                JOIN f1.constructors c ON c.constructor_id = res.constructor_id
                JOIN f1.status st ON st.status_id = res.status_id
                WHERE res.race_id = %s
                ORDER BY res.position_order
                """,
                (race_id,),
            ).fetchall()
        if not rows:
            return "No sprint results found for this Grand Prix."
        finishers = [
            {
                "Position": row["position_text"],
                "Driver": f"{row['forename']} {row['surname']}",
                "Team": row["team"],
                "Gap / Race Time": _cell(row.get("race_time")),
                "Status": _cell(row.get("status")),
                "Fastest Lap": _cell(row.get("fastest_lap_time")),
                "Fastest Lap Number": _cell(row.get("fastest_lap")),
                "Points": row["points"],
            }
            for row in rows
        ]
        return {
            "Year": year,
            "Grand Prix": race_name,
            "Session": "Sprint",
            "Classification": finishers,
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_lap_time_delta(
    year: int,
    country: str,
    driver_a: str,
    driver_b: str,
    lap_number: int,
    location: str | None = None,
) -> dict | str:
    missing = _require()
    if missing:
        return missing
    try:
        race = _resolve_race(year, country, location=location)
        if isinstance(race, str):
            return race
        race_id, race_name = race
        resolved_a = resolve_driver(driver_a)
        resolved_b = resolve_driver(driver_b)
        if resolved_a is None:
            return f"Could not find driver '{driver_a}' in the historical database."
        if resolved_b is None:
            return f"Could not find driver '{driver_b}' in the historical database."
        driver_a_id, driver_a_name = resolved_a
        driver_b_id, driver_b_name = resolved_b

        def _lap(driver_id: int):
            with connect() as conn:
                return conn.execute(
                    """
                    SELECT lap_time, position, milliseconds
                    FROM f1.lap_times
                    WHERE race_id = %s AND driver_id = %s AND lap = %s
                    """,
                    (race_id, driver_id, lap_number),
                ).fetchone()

        lap_a = _lap(driver_a_id)
        lap_b = _lap(driver_b_id)
        if lap_a is None:
            return f"No lap {lap_number} data found for {driver_a_name} in the {year} {race_name}."
        if lap_b is None:
            return f"No lap {lap_number} data found for {driver_b_name} in the {year} {race_name}."
        ms_a = int(lap_a["milliseconds"])
        ms_b = int(lap_b["milliseconds"])
        delta_ms = ms_a - ms_b
        delta_s = abs(delta_ms) / 1000.0
        if delta_ms < 0:
            faster, slower = driver_a_name, driver_b_name
        elif delta_ms > 0:
            faster, slower = driver_b_name, driver_a_name
        else:
            faster, slower = None, None
        return {
            "Year": year,
            "Grand Prix": race_name,
            "Lap": lap_number,
            "Driver A": {
                "Name": driver_a_name,
                "Lap Time": _cell(lap_a["lap_time"]),
                "Position": int(lap_a["position"]),
                "Milliseconds": ms_a,
            },
            "Driver B": {
                "Name": driver_b_name,
                "Lap Time": _cell(lap_b["lap_time"]),
                "Position": int(lap_b["position"]),
                "Milliseconds": ms_b,
            },
            "Delta Milliseconds": delta_ms,
            "Faster Driver": faster,
            "Slower Driver": slower,
            "Delta Seconds": delta_s,
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_max_fastest_lap_speed(
    year: int | None = None,
    country: str | None = None,
    location: str | None = None,
    driver_ref: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> dict | str:
    missing = _require()
    if missing:
        return missing
    try:
        clauses = ["res.fastest_lap_speed IS NOT NULL"]
        params: list = []
        if driver_ref:
            resolved = resolve_driver(driver_ref)
            if resolved is None:
                return f"Could not find driver '{driver_ref}' in the historical database."
            clauses.append("res.driver_id = %s")
            params.append(resolved[0])
        if country:
            races_yr = races_for_venue_df(year, country, location=location) if year is not None else None
            if year is None:
                keywords = csv_race_keywords(country, location)
                if not keywords:
                    return f"No races found matching '{country}'."
                pattern = "|".join(re.escape(k) for k in keywords)
                with connect() as conn:
                    race_rows = conn.execute(
                        'SELECT race_id AS "raceId", name FROM f1.races WHERE name ~* %s',
                        (pattern,),
                    ).fetchall()
                races_yr = pd.DataFrame(race_rows)
            if races_yr is None or races_yr.empty:
                label = location or country
                return f"No races found matching '{label}'" + (f" in {year}." if year else ".")
            if country in MULTI_GP_COUNTRIES and not location and len(races_yr) > 1:
                return multi_gp_clarification(country)
            ids = [int(x) for x in races_yr["raceId"].tolist()]
            clauses.append("res.race_id = ANY(%s)")
            params.append(ids)
        elif year is not None:
            clauses.append("r.year = %s")
            params.append(year)
        else:
            if year_start is not None:
                clauses.append("r.year >= %s")
                params.append(year_start)
            if year_end is not None:
                clauses.append("r.year <= %s")
                params.append(year_end)
        where = " AND ".join(clauses)
        sql = f"""
            SELECT res.fastest_lap_speed, d.forename, d.surname, r.year, r.name AS race_name
            FROM f1.results res
            JOIN f1.races r ON r.race_id = res.race_id
            JOIN f1.drivers d ON d.driver_id = res.driver_id
            WHERE {where}
            ORDER BY res.fastest_lap_speed DESC
            LIMIT 1
        """
        with connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return "No speed data found for those filters."
        return {
            "measurement": "fastest lap speed (CSV)",
            "speed_kmh": float(row["fastest_lap_speed"]),
            "driver": f"{row['forename']} {row['surname']}",
            "year": int(row["year"]),
            "grand_prix": row["race_name"],
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_grand_prix_by_country(country: str) -> list[dict] | str:
    missing = _require()
    if missing:
        return missing
    try:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT r.name, c.location, array_agg(DISTINCT r.year ORDER BY r.year) AS years
                FROM f1.races r
                JOIN f1.circuits c ON c.circuit_id = r.circuit_id
                WHERE lower(c.country) = lower(%s)
                GROUP BY r.name, c.location
                """,
                (country,),
            ).fetchall()
        if not rows:
            return f"No Formula 1 Grands Prix found in {country} in the historical database."
        records = []
        for row in rows:
            years = [int(y) for y in (row["years"] or [])]
            records.append(
                {
                    "grand_prix": row["name"],
                    "location": row["location"],
                    "years": years,
                    "count": len(years),
                    "first_year": years[0],
                    "last_year": years[-1],
                }
            )
        records.sort(key=lambda record: (record["last_year"], record["grand_prix"]), reverse=True)
        return records
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_driver_teams(year: int, driver_ref: str) -> dict | str:
    missing = _require()
    if missing:
        return missing
    try:
        resolved = resolve_driver(driver_ref)
        if resolved is None:
            return f"Could not find driver '{driver_ref}' in the historical database."
        driver_id, full_name = resolved
        with connect() as conn:
            race_count = conn.execute(
                "SELECT COUNT(*) AS n FROM f1.races WHERE year = %s", (year,)
            ).fetchone()
            if not race_count or int(race_count["n"]) == 0:
                return f"No races found for {year}."
            rows = conn.execute(
                """
                SELECT c.name AS team,
                       COUNT(DISTINCT res.race_id) AS races,
                       MIN(r.round) AS first_round,
                       MAX(r.round) AS last_round
                FROM f1.results res
                JOIN f1.races r ON r.race_id = res.race_id
                JOIN f1.constructors c ON c.constructor_id = res.constructor_id
                WHERE res.driver_id = %s AND r.year = %s
                GROUP BY c.name
                ORDER BY MIN(r.round), c.name
                """,
                (driver_id, year),
            ).fetchall()
        if not rows:
            return f"No race entries found for {full_name} in {year}."
        return {
            "Year": year,
            "Driver": full_name,
            "Teams": [
                {
                    "Team": row["team"],
                    "Races": int(row["races"]),
                    "From Round": int(row["first_round"]),
                    "To Round": int(row["last_round"]),
                }
                for row in rows
            ],
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_driver_standing(year: int, driver_ref: str) -> dict | str:
    missing = _require()
    if missing:
        return missing
    try:
        resolved = resolve_driver(driver_ref)
        if resolved is None:
            return f"Could not find driver '{driver_ref}' in the historical database."
        driver_id, full_name = resolved
        with connect() as conn:
            last_race = conn.execute(
                """
                SELECT race_id, round, name
                FROM f1.races
                WHERE year = %s
                ORDER BY round DESC
                LIMIT 1
                """,
                (year,),
            ).fetchone()
            if not last_race:
                return f"No races found for {year}."
            standing = conn.execute(
                """
                SELECT position, position_text, points, wins
                FROM f1.driver_standings
                WHERE driver_id = %s AND race_id = %s
                """,
                (driver_id, last_race["race_id"]),
            ).fetchone()
        if not standing:
            return f"No championship standing found for {full_name} in {year}."
        return {
            "Year": year,
            "Driver": full_name,
            "Position": int(standing["position"]),
            "PositionText": str(standing["position_text"]),
            "Points": float(standing["points"]),
            "Wins": int(standing["wins"]),
            "FinalRound": int(last_race["round"]),
            "FinalRace": last_race["name"],
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"
