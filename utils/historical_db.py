import pandas as pd
import os
import re
from datetime import datetime, timezone

from utils.venues import csv_race_keywords, MULTI_GP_COUNTRIES, multi_gp_clarification

DATA_DIR = "./data/historical_csvs"

CSV_UNAVAILABLE_MESSAGE = (
    "Historical CSV database is not available. "
    "Run: python setup_historical_data.py"
)

# Load ALL the CSVs into memory when the app starts
races_df = None
circuits_df = None
drivers_df = None
constructors_df = None
results_df = None
status_df = None
lap_times_df = None
qualifying_df = None
sprint_results_df = None
driver_standings_df = None

try:
    races_df = pd.read_csv(os.path.join(DATA_DIR, "races.csv"))
    circuits_df = pd.read_csv(os.path.join(DATA_DIR, "circuits.csv"))
    drivers_df = pd.read_csv(os.path.join(DATA_DIR, "drivers.csv"))
    constructors_df = pd.read_csv(os.path.join(DATA_DIR, "constructors.csv"))
    results_df = pd.read_csv(os.path.join(DATA_DIR, "results.csv"))
    status_df = pd.read_csv(os.path.join(DATA_DIR, "status.csv"))
    lap_times_df = pd.read_csv(os.path.join(DATA_DIR, "lap_times.csv"))
    qualifying_df = pd.read_csv(os.path.join(DATA_DIR, "qualifying.csv"))
    sprint_results_df = pd.read_csv(os.path.join(DATA_DIR, "sprint_results.csv"))
    driver_standings_df = pd.read_csv(os.path.join(DATA_DIR, "driver_standings.csv"))
except FileNotFoundError:
    print(f"Warning: {CSV_UNAVAILABLE_MESSAGE}")


def csv_available() -> bool:
    """True when the core Ergast CSV tables loaded successfully."""
    return all(
        frame is not None
        for frame in (
            races_df,
            circuits_df,
            drivers_df,
            constructors_df,
            results_df,
            status_df,
        )
    )


def _require_csv() -> str | None:
    if csv_available():
        return None
    return CSV_UNAVAILABLE_MESSAGE


def _cell(value) -> str:
    if value is None or str(value) in ("\\N", "nan", ""):
        return "N/A"
    return str(value)


def _races_for_venue(year: int, country: str, location: str | None = None) -> pd.DataFrame:
    """Return CSV race rows for a year/country, aggregating all venues when needed."""
    if races_df is None:
        return pd.DataFrame()

    races_yr = races_df[races_df["year"] == year]
    if not country:
        return races_yr

    if country in MULTI_GP_COUNTRIES and not location:
        keywords: list[str] = []
        for _, mapped_location in MULTI_GP_COUNTRIES[country]:
            keywords.extend(csv_race_keywords(country, mapped_location))
    else:
        keywords = csv_race_keywords(country, location)

    if not keywords:
        return races_yr.iloc[0:0]

    pattern = "|".join(re.escape(k) for k in keywords)
    return races_yr[races_yr["name"].str.contains(pattern, case=False, na=False)]


def get_race_results(year: int, country: str, top_n: int | None = None, location: str | None = None) -> dict | str:
    """Return the full race classification, including DNFs and each driver's fastest lap."""
    from utils.race_schedule import (
        RACE_NOT_HELD_RESULTS_MESSAGE,
        _parse_race_date,
        race_results_unavailable_reason,
    )

    missing = _require_csv()
    if missing:
        return missing

    try:
        races_yr = _races_for_venue(year, country, location=location)

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

        race_id = races_yr.iloc[0]['raceId']
        race_name = races_yr.iloc[0]['name']

        res = (
            results_df[results_df['raceId'] == race_id]
            .merge(drivers_df[['driverId', 'forename', 'surname']], on='driverId')
            .merge(constructors_df[['constructorId', 'name']], on='constructorId')
            .merge(status_df, on='statusId', how='left')
            .sort_values('positionOrder')
        )
        if top_n is not None:
            res = res.head(top_n)

        finishers = []
        overall_fl = None
        for _, row in res.iterrows():
            gap = _cell(row['time'])
            fl_time = _cell(row['fastestLapTime'])
            entry = {
                "Position": row['positionText'],
                "Driver": f"{row['forename']} {row['surname']}",
                "Team": row['name'],
                "Gap / Race Time": gap,
                "Status": _cell(row.get('status')),
                "Fastest Lap": fl_time,
                "Fastest Lap Number": _cell(row.get('fastestLap')),
                "Points": row['points'],
            }
            finishers.append(entry)
            if pd.to_numeric(row.get('rank'), errors='coerce') == 1 and fl_time != "N/A":
                overall_fl = {
                    "Driver": entry["Driver"],
                    "Time": fl_time,
                    "Lap": entry["Fastest Lap Number"],
                }

        packet = {
            "Year": year,
            "Grand Prix": race_name,
            "Classification": finishers,
        }
        if overall_fl:
            packet["Overall Fastest Lap"] = overall_fl
        return packet
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def _session_results_common(
    year: int,
    country: str,
    location: str | None,
    results_frame: pd.DataFrame | None,
    empty_message: str,
) -> tuple[int, str, pd.DataFrame] | str:
    from utils.race_schedule import (
        RACE_NOT_HELD_RESULTS_MESSAGE,
        _parse_race_date,
        race_results_unavailable_reason,
    )

    missing = _require_csv()
    if missing:
        return missing
    if results_frame is None:
        return empty_message

    try:
        races_yr = _races_for_venue(year, country, location=location)

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

        race_id = races_yr.iloc[0]["raceId"]
        race_name = races_yr.iloc[0]["name"]
        session_rows = results_frame[results_frame["raceId"] == race_id]
        if session_rows.empty:
            return empty_message

        return race_id, race_name, session_rows
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_qualifying_results(
    year: int,
    country: str,
    location: str | None = None,
) -> dict | str:
    """Return qualifying grid data for a Grand Prix."""
    lookup = _session_results_common(
        year,
        country,
        location,
        qualifying_df,
        "No qualifying results found for this Grand Prix.",
    )
    if not isinstance(lookup, tuple):
        return lookup

    race_id, race_name, session_rows = lookup
    try:
        qual = (
            session_rows.merge(drivers_df[["driverId", "forename", "surname"]], on="driverId")
            .merge(constructors_df[["constructorId", "name"]], on="constructorId")
            .sort_values("position")
        )
        grid = []
        for _, row in qual.iterrows():
            grid.append(
                {
                    "Position": int(row["position"]),
                    "Driver": f"{row['forename']} {row['surname']}",
                    "Team": row["name"],
                    "Q1": _cell(row.get("q1")),
                    "Q2": _cell(row.get("q2")),
                    "Q3": _cell(row.get("q3")),
                }
            )
        return {
            "Year": year,
            "Grand Prix": race_name,
            "Session": "Qualifying",
            "Grid": grid,
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_sprint_results(
    year: int,
    country: str,
    location: str | None = None,
) -> dict | str:
    """Return sprint classification data for a Grand Prix."""
    lookup = _session_results_common(
        year,
        country,
        location,
        sprint_results_df,
        "No sprint results found for this Grand Prix.",
    )
    if not isinstance(lookup, tuple):
        return lookup

    race_id, race_name, session_rows = lookup
    try:
        res = (
            session_rows.merge(drivers_df[["driverId", "forename", "surname"]], on="driverId")
            .merge(constructors_df[["constructorId", "name"]], on="constructorId")
            .merge(status_df, on="statusId", how="left")
            .sort_values("positionOrder")
        )
        finishers = []
        for _, row in res.iterrows():
            finishers.append(
                {
                    "Position": row["positionText"],
                    "Driver": f"{row['forename']} {row['surname']}",
                    "Team": row["name"],
                    "Gap / Race Time": _cell(row["time"]),
                    "Status": _cell(row.get("status")),
                    "Fastest Lap": _cell(row.get("fastestLapTime")),
                    "Fastest Lap Number": _cell(row.get("fastestLap")),
                    "Points": row["points"],
                }
            )
        return {
            "Year": year,
            "Grand Prix": race_name,
            "Session": "Sprint",
            "Classification": finishers,
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def format_qualifying_grid(packet: dict) -> str:
    """Render qualifying times as a starting grid."""
    year = packet.get("Year")
    gp = packet.get("Grand Prix")
    grid = packet.get("Grid") or []
    lines = [f"The qualifying results for the {year} {gp} are as follows:", ""]
    lines.append(f"Starting grid ({len(grid)}):")
    for row in grid:
        segments = []
        for segment in ("Q1", "Q2", "Q3"):
            value = row.get(segment)
            if value and value != "N/A":
                segments.append(f"{segment}: {value}")
        times = ", ".join(segments) if segments else "no time recorded"
        lines.append(
            f"P{row.get('Position')}. {row.get('Driver')} ({row.get('Team')}) - {times}"
        )
    return "\n".join(lines)


def format_session_classification(packet: dict) -> str:
    """Render race or sprint classification packets."""
    session = packet.get("Session") or "Race"
    text = format_race_classification(packet)
    if session == "Sprint":
        return text.replace("The results for the", "The sprint results for the", 1)
    return text


_NON_CLASSIFIED_POS = {"R", "D", "W", "N", "E", "F"}


def _format_points(pts) -> str:
    value = float(pts) if pts is not None else 0.0
    label = "pt" if value == 1.0 else "pts"
    return f"{value:.1f} {label}"


def _classified_gap(row: dict) -> str:
    gap = row.get("Gap / Race Time")
    if gap and gap != "N/A":
        return gap
    return row.get("Status") or "N/A"


def _retirement_cause(row: dict) -> str:
    return row.get("Status") or "Retired"


def format_race_classification(packet: dict) -> str:
    """Render the full grid with classified finishers and retirements in separate sections."""
    classified = []
    retired = []
    for row in packet.get("Classification") or []:
        pos = str(row.get("Position", "")).strip()
        if pos in _NON_CLASSIFIED_POS or not pos.isdigit():
            retired.append(row)
        else:
            classified.append(row)

    year = packet.get("Year")
    gp = packet.get("Grand Prix")
    lines = [f"The results for the {year} {gp} are as follows:", ""]

    lines.append(f"Classified finishers ({len(classified)}):")
    for index, row in enumerate(classified, start=1):
        gap = _classified_gap(row)
        fl = row.get("Fastest Lap")
        fl_lap = row.get("Fastest Lap Number")
        fl_part = f", fastest lap {fl} on lap {fl_lap}" if fl and fl != "N/A" else ""
        status = row.get("Status") or ""
        status_part = ""
        if status and status not in ("Finished", "N/A") and not status.startswith("+"):
            status_part = f" [{status}]"
        lines.append(
            f"{index}. {row.get('Driver')} ({row.get('Team')}) - "
            f"{gap}, {_format_points(row.get('Points'))}{status_part}{fl_part}"
        )

    lines.append("")
    if retired:
        lines.append(f"Did not finish ({len(retired)}):")
        for row in retired:
            lines.append(
                f"- {row.get('Driver')} ({row.get('Team')}) — "
                f"Cause: {_retirement_cause(row)}, {_format_points(row.get('Points'))}"
            )
    else:
        lines.append("Did not finish: none recorded for this race.")

    overall = packet.get("Overall Fastest Lap")
    if overall:
        lines.append("")
        lines.append(
            f"The overall fastest lap was set by {overall.get('Driver')} "
            f"with a time of {overall.get('Time')} on lap {overall.get('Lap')}."
        )

    queried = packet.get("Queried Driver")
    if queried:
        lines.append("")
        lines.append(
            f"Queried driver: {queried.get('Driver')} ({queried.get('Team')}) — "
            f"P{queried.get('Finish Position')}, fastest lap {queried.get('Fastest Lap')}"
        )
    return "\n".join(lines)


def _resolve_driver(driver_ref: str) -> tuple[int, str] | None:
    if drivers_df is None:
        return None
    if not driver_ref or not str(driver_ref).strip():
        return None
    ref = str(driver_ref).strip()

    def _row_to_tuple(row) -> tuple[int, str]:
        return int(row["driverId"]), f"{row['forename']} {row['surname']}"

    if "driverRef" in drivers_df.columns:
        slug = ref.lower().replace(" ", "_")
        match = drivers_df[drivers_df["driverRef"].str.lower() == slug]
        if not match.empty:
            return _row_to_tuple(match.iloc[0])

    parts = ref.split()
    if len(parts) >= 2:
        forename, surname = parts[0], parts[-1]
        match = drivers_df[
            drivers_df["forename"].str.contains(forename, case=False, na=False)
            & drivers_df["surname"].str.contains(surname, case=False, na=False)
        ]
        if not match.empty:
            return _row_to_tuple(match.iloc[0])

        full_names = drivers_df["forename"] + " " + drivers_df["surname"]
        match = drivers_df[full_names.str.contains(ref, case=False, na=False)]
        if not match.empty:
            return _row_to_tuple(match.iloc[0])

    match = drivers_df[drivers_df["surname"].str.contains(ref, case=False, na=False)]
    if match.empty:
        match = drivers_df[drivers_df["forename"].str.contains(ref, case=False, na=False)]
    if match.empty:
        return None
    return _row_to_tuple(match.iloc[0])


def _resolve_race(year: int, country: str, location: str | None = None) -> tuple[int, str] | str:
    races_yr = _races_for_venue(year, country, location=location)
    if races_yr.empty:
        return f"No races found for {year}" + (f" matching '{country}'." if country else ".")
    if country in MULTI_GP_COUNTRIES and not location and len(races_yr) > 1:
        return multi_gp_clarification(country)
    row = races_yr.iloc[0]
    return int(row["raceId"]), row["name"]


def _driver_lap_row(race_id: int, driver_id: int, lap_number: int) -> pd.Series | None:
    if lap_times_df is None:
        return None
    rows = lap_times_df[
        (lap_times_df["raceId"] == race_id)
        & (lap_times_df["driverId"] == driver_id)
        & (lap_times_df["lap"] == lap_number)
    ]
    if rows.empty:
        return None
    return rows.iloc[0]


def get_lap_time_delta(
    year: int,
    country: str,
    driver_a: str,
    driver_b: str,
    lap_number: int,
    location: str | None = None,
) -> dict | str:
    """Return lap-time comparison for two drivers on a specific lap."""
    missing = _require_csv()
    if missing:
        return missing

    try:
        if lap_times_df is None:
            return CSV_UNAVAILABLE_MESSAGE

        race = _resolve_race(year, country, location=location)
        if isinstance(race, str):
            return race
        race_id, race_name = race

        resolved_a = _resolve_driver(driver_a)
        resolved_b = _resolve_driver(driver_b)
        if resolved_a is None:
            return f"Could not find driver '{driver_a}' in the historical database."
        if resolved_b is None:
            return f"Could not find driver '{driver_b}' in the historical database."

        driver_a_id, driver_a_name = resolved_a
        driver_b_id, driver_b_name = resolved_b
        lap_a = _driver_lap_row(race_id, driver_a_id, lap_number)
        lap_b = _driver_lap_row(race_id, driver_b_id, lap_number)

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
                "Lap Time": _cell(lap_a["time"]),
                "Position": int(lap_a["position"]),
                "Milliseconds": ms_a,
            },
            "Driver B": {
                "Name": driver_b_name,
                "Lap Time": _cell(lap_b["time"]),
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


def format_lap_time_delta(packet: dict) -> str:
    """Render a lap-time delta packet as plain text."""
    a = packet["Driver A"]
    b = packet["Driver B"]
    lines = [
        f"On lap {packet['Lap']} of the {packet['Year']} {packet['Grand Prix']}:",
        "",
        f"- {a['Name']}: {a['Lap Time']} (P{a['Position']})",
        f"- {b['Name']}: {b['Lap Time']} (P{b['Position']})",
        "",
    ]
    if packet.get("Faster Driver"):
        lines.append(
            f"{packet['Faster Driver']} was {packet['Delta Seconds']:.3f}s faster than "
            f"{packet['Slower Driver']} on that lap."
        )
    else:
        lines.append("Both drivers posted the same lap time on that lap.")
    return "\n".join(lines)


def get_max_fastest_lap_speed(
    year: int | None = None,
    country: str | None = None,
    location: str | None = None,
    driver_ref: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> dict | str:
    """Return the highest fastestLapSpeed from results.csv for the given scope."""
    missing = _require_csv()
    if missing:
        return missing

    try:
        merged = results_df.merge(
            races_df[["raceId", "year", "name"]].rename(columns={"name": "race_name"}),
            on="raceId",
        ).merge(
            drivers_df[["driverId", "forename", "surname"]],
            on="driverId",
        )
        merged["fastestLapSpeed"] = pd.to_numeric(merged["fastestLapSpeed"], errors="coerce")
        merged = merged[merged["fastestLapSpeed"].notna()]

        if driver_ref:
            resolved = _resolve_driver(driver_ref)
            if resolved is None:
                return f"Could not find driver '{driver_ref}' in the historical database."
            merged = merged[merged["driverId"] == resolved[0]]

        if country:
            if year is not None:
                races_yr = _races_for_venue(year, country, location=location)
            else:
                keywords = csv_race_keywords(country, location)
                if not keywords:
                    return f"No races found matching '{country}'."
                pattern = "|".join(re.escape(k) for k in keywords)
                races_yr = races_df[races_df["name"].str.contains(pattern, case=False, na=False)]
            if races_yr.empty:
                label = location or country
                return f"No races found matching '{label}'" + (f" in {year}." if year else ".")
            if country in MULTI_GP_COUNTRIES and not location and len(races_yr) > 1:
                return multi_gp_clarification(country)
            merged = merged[merged["raceId"].isin(races_yr["raceId"])]
        elif year is not None:
            merged = merged[merged["year"] == year]
        else:
            if year_start is not None:
                merged = merged[merged["year"] >= year_start]
            if year_end is not None:
                merged = merged[merged["year"] <= year_end]

        if merged.empty:
            return "No speed data found for those filters."

        row = merged.loc[merged["fastestLapSpeed"].idxmax()]
        return {
            "measurement": "fastest lap speed (CSV)",
            "speed_kmh": float(row["fastestLapSpeed"]),
            "driver": f"{row['forename']} {row['surname']}",
            "year": int(row["year"]),
            "grand_prix": row["race_name"],
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def format_top_speed_packet(packet: dict) -> str:
    """Render one top-speed lookup packet as plain text."""
    lines = [
        f"{packet['speed_kmh']:.1f} km/h — {packet['driver']}",
    ]
    if packet.get("race"):
        lines[0] += f" ({packet['race']})"
    elif packet.get("year") and packet.get("grand_prix"):
        lines[0] += f" ({packet['year']} {packet['grand_prix']})"
    if packet.get("team"):
        lines.append(f"Team: {packet['team']}.")
    detail = packet.get("speed_field_label") or packet.get("measurement")
    if packet.get("session"):
        lines.append(f"Session: {packet['session']}.")
    if packet.get("lap_number") is not None:
        lines.append(
            f"Recorded on lap {packet['lap_number']}"
            + (f" at the {detail}" if detail else "")
            + "."
        )
    elif detail:
        lines.append(f"Metric: {detail}.")
    return "\n".join(lines)


def format_top_speed_lookup(
    packets: list[dict],
    *,
    scope: str,
    include_csv_note: bool = False,
    csv_secondary: dict | None = None,
) -> str:
    """Render combined top-speed results."""
    if not packets:
        return "No speed data found for that query."

    lines = [f"Top speed lookup ({scope}):", ""]
    for packet in packets:
        lines.append(f"- {format_top_speed_packet(packet)}")

    if csv_secondary:
        lines.extend(
            [
                "",
                "For comparison, the highest CSV fastest-lap speed in the same scope is "
                f"{csv_secondary['speed_kmh']:.1f} km/h ({csv_secondary['driver']}, "
                f"{csv_secondary['year']} {csv_secondary['grand_prix']}). "
                "That metric is the average speed on a driver's fastest lap, not the "
                "peak speed-trap reading.",
            ]
        )
    elif include_csv_note:
        lines.extend(
            [
                "",
                "Note: CSV fastestLapSpeed is the average speed on a driver's fastest lap "
                "(typically ~240–260 km/h), not the peak speed-trap reading (often 330+ km/h). "
                "Published speed-trap records and OpenF1 data are used when available.",
            ]
        )
    return "\n".join(lines)


def get_grand_prix_by_country(country: str) -> list[dict] | str:
    """Return Grand Prix events held in a country from races.csv + circuits.csv."""
    missing = _require_csv()
    if missing:
        return missing

    try:
        merged = races_df.merge(
            circuits_df[["circuitId", "location", "country"]],
            on="circuitId",
            how="inner",
        )
        country_races = merged[merged["country"].str.casefold() == country.casefold()].copy()
        if country_races.empty:
            return f"No Formula 1 Grands Prix found in {country} in the historical database."

        grouped = (
            country_races.groupby("name", sort=True)
            .agg(
                years=("year", lambda values: sorted({int(value) for value in values})),
                location=("location", "first"),
            )
            .reset_index()
        )

        records: list[dict] = []
        for row in grouped.itertuples(index=False):
            years = list(row.years)
            records.append(
                {
                    "grand_prix": row.name,
                    "location": row.location,
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


def format_country_grand_prix_listing(country: str) -> str:
    """Render a readable list of GPs held in a country."""
    result = get_grand_prix_by_country(country)
    if isinstance(result, str):
        return result

    lines = [f"Formula 1 Grands Prix held in {country}:"]
    for record in result:
        years = record["years"]
        if record["count"] == 1:
            year_text = str(years[0])
        elif record["count"] <= 4:
            year_text = ", ".join(str(year) for year in years)
        else:
            year_text = f"{record['first_year']}–{record['last_year']} ({record['count']} seasons)"
        lines.append(f"- {record['grand_prix']} ({record['location']}) — {year_text}")
    lines.append(f"\nTotal: {sum(record['count'] for record in result)} race(s) across {len(result)} Grand Prix name(s).")
    return "\n".join(lines)


def format_country_grand_prix_listing_answer(query: str, countries: list[str]) -> str | None:
    if not countries:
        return None
    sections = [format_country_grand_prix_listing(country) for country in countries]
    return "\n\n".join(sections)


def get_driver_teams(year: int, driver_ref: str) -> dict | str:
    """Return the team(s) a driver raced for in a given season."""
    missing = _require_csv()
    if missing:
        return missing

    try:
        resolved = _resolve_driver(driver_ref)
        if resolved is None:
            return f"Could not find driver '{driver_ref}' in the historical database."

        driver_id, full_name = resolved
        season_races = races_df[races_df["year"] == year]
        if season_races.empty:
            return f"No races found for {year}."

        race_ids = season_races["raceId"]
        entries = results_df[
            (results_df["driverId"] == driver_id) & (results_df["raceId"].isin(race_ids))
        ].merge(
            constructors_df[["constructorId", "name"]].rename(columns={"name": "team"}),
            on="constructorId",
        ).merge(
            season_races[["raceId", "name", "round"]].rename(columns={"name": "race_name"}),
            on="raceId",
        )

        if entries.empty:
            return f"No race entries found for {full_name} in {year}."

        teams = (
            entries.groupby("team", as_index=False)
            .agg(
                races=("raceId", "nunique"),
                first_round=("round", "min"),
                last_round=("round", "max"),
            )
            .sort_values(["first_round", "team"])
        )

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
                for _, row in teams.iterrows()
            ],
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def format_driver_teams(packet: dict) -> str:
    """Render a driver-team lookup as plain text."""
    lines = [f"In {packet['Year']}, {packet['Driver']} raced for:"]
    for entry in packet["Teams"]:
        if entry["From Round"] == entry["To Round"]:
            round_span = f"round {entry['From Round']}"
        else:
            round_span = f"rounds {entry['From Round']}–{entry['To Round']}"
        race_word = "race" if entry["Races"] == 1 else "races"
        lines.append(
            f"- {entry['Team']} ({entry['Races']} {race_word}, {round_span})"
        )
    if len(packet["Teams"]) == 1:
        lines.append("")
        lines.append(f"{packet['Driver']} drove for {packet['Teams'][0]['Team']} all season.")
    return "\n".join(lines)


def get_driver_standing(year: int, driver_ref: str) -> dict | str:
    """Return a driver's end-of-season championship position and points."""
    missing = _require_csv()
    if missing:
        return missing
    if driver_standings_df is None:
        return "Driver standings data is not available in the historical CSV database."

    try:
        resolved = _resolve_driver(driver_ref)
        if resolved is None:
            return f"Could not find driver '{driver_ref}' in the historical database."

        driver_id, full_name = resolved
        season_races = races_df[races_df["year"] == year]
        if season_races.empty:
            return f"No races found for {year}."

        last_race = season_races.sort_values("round").iloc[-1]
        last_race_id = int(last_race["raceId"])
        standing = driver_standings_df[
            (driver_standings_df["driverId"] == driver_id)
            & (driver_standings_df["raceId"] == last_race_id)
        ]
        if standing.empty:
            return f"No championship standing found for {full_name} in {year}."

        row = standing.iloc[0]
        return {
            "Year": year,
            "Driver": full_name,
            "Position": int(row["position"]),
            "PositionText": str(row["positionText"]),
            "Points": float(row["points"]),
            "Wins": int(row["wins"]),
            "FinalRound": int(last_race["round"]),
            "FinalRace": last_race["name"],
        }
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def _ordinal(position: int) -> str:
    if 10 <= position % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")
    return f"{position}{suffix}"


def format_driver_standing(packet: dict) -> str:
    """Render a driver's end-of-season championship result."""
    position = int(packet["Position"])
    points = packet["Points"]
    wins = int(packet["Wins"])
    points_text = f"{points:.0f}" if points == int(points) else f"{points:.1f}"
    win_word = "win" if wins == 1 else "wins"
    return (
        f"In the {packet['Year']} Formula 1 World Championship, "
        f"{packet['Driver']} finished {_ordinal(position)} "
        f"with {points_text} points and {wins} race {win_word}."
    )


def get_historical_driver_info(year: int, driver_ref: str, country: str = None, location: str | None = None):
    """Return a driver's result plus the full race classification for that event."""
    missing = _require_csv()
    if missing:
        return missing

    try:
        # Always fetch the full race results for rich context
        race_data = get_race_results(year, country, location=location)
        if isinstance(race_data, str):
            return race_data  # error string

        if not driver_ref:
            return race_data  # no specific driver — return full results

        resolved = _resolve_driver(driver_ref)
        if resolved is None:
            return race_data

        driver_id, full_name = resolved

        races_yr = races_df[races_df['year'] == year]
        if country:
            keywords = csv_race_keywords(country, location)
            if keywords:
                pattern = "|".join(re.escape(k) for k in keywords)
                races_yr = races_yr[races_yr['name'].str.contains(pattern, case=False, na=False)]

        if not races_yr.empty:
            race_id = races_yr.iloc[0]['raceId']
            res = results_df[(results_df['raceId'] == race_id) & (results_df['driverId'] == driver_id)]
            if not res.empty:
                constructor_id = res.iloc[0]['constructorId']
                team_name = constructors_df[constructors_df['constructorId'] == constructor_id].iloc[0]['name']
                race_data["Queried Driver"] = {
                    "Driver": full_name,
                    "Team": team_name,
                    "Finish Position": res.iloc[0]['positionText'],
                    "Gap / Race Time": res.iloc[0]['time'] if str(res.iloc[0]['time']) not in ('\\N', 'nan', '') else 'N/A',
                    "Fastest Lap": res.iloc[0]['fastestLapTime'] if str(res.iloc[0]['fastestLapTime']) not in ('\\N', 'nan', '') else 'N/A',
                    "Points": res.iloc[0]['points'],
                }

        return race_data
    except Exception as e:
        return f"Historical Database Error: {str(e)}"