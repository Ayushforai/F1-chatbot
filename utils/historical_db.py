import pandas as pd
import os
import re

from utils.venues import csv_race_keywords, MULTI_GP_COUNTRIES, multi_gp_clarification

DATA_DIR = "./data/historical_csvs"

# Load ALL the CSVs into memory when the app starts
try:
    races_df = pd.read_csv(os.path.join(DATA_DIR, "races.csv"))
    drivers_df = pd.read_csv(os.path.join(DATA_DIR, "drivers.csv"))
    constructors_df = pd.read_csv(os.path.join(DATA_DIR, "constructors.csv"))
    results_df = pd.read_csv(os.path.join(DATA_DIR, "results.csv"))
    status_df = pd.read_csv(os.path.join(DATA_DIR, "status.csv"))
    lap_times_df = pd.read_csv(os.path.join(DATA_DIR, "lap_times.csv"))
except FileNotFoundError:
    print("Warning: Historical CSVs not found. Please run setup_historical_data.py first.")
    lap_times_df = None


def _cell(value) -> str:
    if value is None or str(value) in ("\\N", "nan", ""):
        return "N/A"
    return str(value)


def _races_for_venue(year: int, country: str, location: str | None = None) -> pd.DataFrame:
    """Return CSV race rows for a year/country, aggregating all venues when needed."""
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
    try:
        races_yr = _races_for_venue(year, country, location=location)

        if races_yr.empty:
            return f"No races found for {year}" + (f" matching '{country}'." if country else ".")

        if country in MULTI_GP_COUNTRIES and not location and len(races_yr) > 1:
            return multi_gp_clarification(country)

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
    try:
        if lap_times_df is None:
            return "Historical lap-time data is not available. Run setup_historical_data.py first."

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


def get_driver_teams(year: int, driver_ref: str) -> dict | str:
    """Return the team(s) a driver raced for in a given season."""
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


def get_historical_driver_info(year: int, driver_ref: str, country: str = None, location: str | None = None):
    """Return a driver's result plus the full race classification for that event."""
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