"""Load data/historical_csvs into PostgreSQL f1.* tables."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from utils.db import apply_schema, connect, database_url, reset_backend_cache

DATA_DIR = ROOT / "data" / "historical_csvs"

# CSV header -> SQL column. Load order respects foreign keys.
TABLES: list[tuple[str, str, dict[str, str]]] = [
    ("seasons.csv", "f1.seasons", {"year": "year", "url": "url"}),
    (
        "circuits.csv",
        "f1.circuits",
        {
            "circuitId": "circuit_id",
            "circuitRef": "circuit_ref",
            "name": "name",
            "location": "location",
            "country": "country",
            "lat": "lat",
            "lng": "lng",
            "alt": "alt",
            "url": "url",
        },
    ),
    (
        "drivers.csv",
        "f1.drivers",
        {
            "driverId": "driver_id",
            "driverRef": "driver_ref",
            "number": "number",
            "code": "code",
            "forename": "forename",
            "surname": "surname",
            "dob": "dob",
            "nationality": "nationality",
            "url": "url",
        },
    ),
    (
        "constructors.csv",
        "f1.constructors",
        {
            "constructorId": "constructor_id",
            "constructorRef": "constructor_ref",
            "name": "name",
            "nationality": "nationality",
            "url": "url",
        },
    ),
    ("status.csv", "f1.status", {"statusId": "status_id", "status": "status"}),
    (
        "races.csv",
        "f1.races",
        {
            "raceId": "race_id",
            "year": "year",
            "round": "round",
            "circuitId": "circuit_id",
            "name": "name",
            "date": "race_date",
            "time": "race_time",
            "url": "url",
            "fp1_date": "fp1_date",
            "fp1_time": "fp1_time",
            "fp2_date": "fp2_date",
            "fp2_time": "fp2_time",
            "fp3_date": "fp3_date",
            "fp3_time": "fp3_time",
            "quali_date": "quali_date",
            "quali_time": "quali_time",
            "sprint_date": "sprint_date",
            "sprint_time": "sprint_time",
        },
    ),
    (
        "results.csv",
        "f1.results",
        {
            "resultId": "result_id",
            "raceId": "race_id",
            "driverId": "driver_id",
            "constructorId": "constructor_id",
            "number": "car_number",
            "grid": "grid",
            "position": "position",
            "positionText": "position_text",
            "positionOrder": "position_order",
            "points": "points",
            "laps": "laps",
            "time": "race_time",
            "milliseconds": "milliseconds",
            "fastestLap": "fastest_lap",
            "rank": "fastest_lap_rank",
            "fastestLapTime": "fastest_lap_time",
            "fastestLapSpeed": "fastest_lap_speed",
            "statusId": "status_id",
        },
    ),
    (
        "qualifying.csv",
        "f1.qualifying",
        {
            "qualifyId": "qualify_id",
            "raceId": "race_id",
            "driverId": "driver_id",
            "constructorId": "constructor_id",
            "number": "car_number",
            "position": "position",
            "q1": "q1",
            "q2": "q2",
            "q3": "q3",
        },
    ),
    (
        "sprint_results.csv",
        "f1.sprint_results",
        {
            "resultId": "result_id",
            "raceId": "race_id",
            "driverId": "driver_id",
            "constructorId": "constructor_id",
            "number": "car_number",
            "grid": "grid",
            "position": "position",
            "positionText": "position_text",
            "positionOrder": "position_order",
            "points": "points",
            "laps": "laps",
            "time": "race_time",
            "milliseconds": "milliseconds",
            "fastestLap": "fastest_lap",
            "fastestLapTime": "fastest_lap_time",
            "statusId": "status_id",
        },
    ),
    (
        "lap_times.csv",
        "f1.lap_times",
        {
            "raceId": "race_id",
            "driverId": "driver_id",
            "lap": "lap",
            "position": "position",
            "time": "lap_time",
            "milliseconds": "milliseconds",
        },
    ),
    (
        "pit_stops.csv",
        "f1.pit_stops",
        {
            "raceId": "race_id",
            "driverId": "driver_id",
            "stop": "stop",
            "lap": "lap",
            "time": "stop_time",
            "duration": "duration",
            "milliseconds": "milliseconds",
        },
    ),
    (
        "driver_standings.csv",
        "f1.driver_standings",
        {
            "driverStandingsId": "driver_standings_id",
            "raceId": "race_id",
            "driverId": "driver_id",
            "points": "points",
            "position": "position",
            "positionText": "position_text",
            "wins": "wins",
        },
    ),
    (
        "constructor_results.csv",
        "f1.constructor_results",
        {
            "constructorResultsId": "constructor_results_id",
            "raceId": "race_id",
            "constructorId": "constructor_id",
            "points": "points",
            "status": "status",
        },
    ),
    (
        "constructor_standings.csv",
        "f1.constructor_standings",
        {
            "constructorStandingsId": "constructor_standings_id",
            "raceId": "race_id",
            "constructorId": "constructor_id",
            "points": "points",
            "position": "position",
            "positionText": "position_text",
            "wins": "wins",
        },
    ),
]


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, na_values=["\\N"], keep_default_na=True)


_INTEGER_SQL_COLUMNS = {
    "year",
    "circuit_id",
    "driver_id",
    "constructor_id",
    "status_id",
    "race_id",
    "round",
    "result_id",
    "car_number",
    "grid",
    "position",
    "position_order",
    "laps",
    "milliseconds",
    "fastest_lap",
    "fastest_lap_rank",
    "qualify_id",
    "lap",
    "stop",
    "driver_standings_id",
    "constructor_results_id",
    "constructor_standings_id",
    "wins",
    "alt",
    "number",
}


def _prepare(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    missing = [col for col in mapping if col not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    out = df[list(mapping.keys())].rename(columns=mapping)
    for col in out.columns:
        if col in _INTEGER_SQL_COLUMNS:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out


def _copy_frame(conn, table: str, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    buf = io.StringIO()
    frame.to_csv(buf, index=False, na_rep="")
    buf.seek(0)
    cols = ", ".join(frame.columns)
    copy_sql = (
        f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT CSV, HEADER true, NULL '')"
    )
    with conn.cursor() as cur:
        with cur.copy(copy_sql) as copy:
            copy.write(buf.getvalue())
    return len(frame)


def load_archive(data_dir: Path, *, apply: bool) -> dict[str, int]:
    if apply:
        apply_schema(include_pgvector=True)
    counts: dict[str, int] = {}
    with connect() as conn:
        conn.execute("TRUNCATE f1.seasons CASCADE")
        seasons_path = data_dir / "seasons.csv"
        races_path = data_dir / "races.csv"
        if not seasons_path.is_file() and races_path.is_file():
            races = _read_csv(races_path)
            years = sorted({int(y) for y in races["year"].dropna().unique()})
            frame = pd.DataFrame({"year": years, "url": [None] * len(years)})
            counts["f1.seasons"] = _copy_frame(conn, "f1.seasons", frame)
        for filename, table, mapping in TABLES:
            path = data_dir / filename
            if not path.is_file():
                print(f" skip {filename} (not found)")
                continue
            df = _prepare(_read_csv(path), mapping)
            if table == "f1.seasons" and table in counts:
                continue
            counts[table] = _copy_frame(conn, table, df)
            print(f" loaded {table}: {counts[table]} rows")
        dup = conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
                SELECT race_id, driver_id FROM f1.results
                GROUP BY race_id, driver_id HAVING COUNT(*) > 1
            ) d
            """
        ).fetchone()
        counts["_duplicate_result_keys"] = int(dup["n"]) if dup else 0
    reset_backend_cache()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Ergast CSVs into PostgreSQL.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--skip-schema", action="store_true")
    args = parser.parse_args()
    if not database_url():
        print("DATABASE_URL is not set.")
        return 1
    if not args.data_dir.is_dir():
        print(f"Data directory not found: {args.data_dir}")
        return 1
    counts = load_archive(args.data_dir, apply=not args.skip_schema)
    print("Done.", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
