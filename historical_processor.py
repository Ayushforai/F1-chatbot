import os
import pandas as pd
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from utils.embeddings import get_embeddings

DATA_DIR = "./data/historical_csvs"
OUTPUT_DIR = "./vector_store/historical"


def _clean(value) -> str:
    if value is None or str(value) in ("\\N", "nan", ""):
        return "N/A"
    return str(value)


def _classification_line(row) -> str:
    """One grid line: position, driver, team, race time or DNF, points, fastest lap."""
    fl = _clean(row.get("fastestLapTime"))
    fl_lap = _clean(row.get("fastestLap"))
    if fl != "N/A" and fl_lap != "N/A":
        pace = f", fastest lap {fl} (lap {fl_lap})"
    elif fl != "N/A":
        pace = f", fastest lap {fl}"
    else:
        pace = ""

    status = _clean(row.get("status"))
    time_or_gap = _clean(row.get("time"))
    if time_or_gap == "N/A" and status not in ("N/A", "Finished"):
        time_or_gap = status

    extra_status = ""
    if status not in ("N/A", "Finished") and time_or_gap != status:
        extra_status = f" [{status}]"

    return (
        f"P{_clean(row['positionText'])}: {row['forename']} {row['surname']} "
        f"({row['constructor_name']}) — {time_or_gap}, {_clean(row['points'])} pts"
        f"{pace}{extra_status}"
    )


def _overall_fastest_lap_line(race_rows: pd.DataFrame) -> str:
    ranked = race_rows.copy()
    ranked["_rank"] = pd.to_numeric(ranked["rank"], errors="coerce")
    best = ranked[ranked["_rank"] == 1]
    if best.empty:
        with_time = ranked[ranked["fastestLapTime"].apply(_clean) != "N/A"]
        if with_time.empty:
            return ""
        best = with_time
    row = best.iloc[0]
    lap_no = _clean(row.get("fastestLap"))
    lap_bit = f" on lap {lap_no}" if lap_no != "N/A" else ""
    return (
        f"Overall fastest lap: {row['forename']} {row['surname']} "
        f"{_clean(row['fastestLapTime'])}{lap_bit}."
    )


def build_historical_documents() -> list[Document]:
    races = pd.read_csv(os.path.join(DATA_DIR, "races.csv"))
    drivers = pd.read_csv(os.path.join(DATA_DIR, "drivers.csv"))
    constructors = pd.read_csv(os.path.join(DATA_DIR, "constructors.csv"))
    results = pd.read_csv(os.path.join(DATA_DIR, "results.csv"))
    standings = pd.read_csv(os.path.join(DATA_DIR, "driver_standings.csv"))
    status = pd.read_csv(os.path.join(DATA_DIR, "status.csv"))

    merged = (
        results.merge(drivers[["driverId", "forename", "surname"]], on="driverId")
        .merge(
            constructors[["constructorId", "name"]].rename(columns={"name": "constructor_name"}),
            on="constructorId",
        )
        .merge(
            races[["raceId", "year", "round", "name"]].rename(columns={"name": "race_name"}),
            on="raceId",
        )
        .merge(status, on="statusId", how="left")
        .sort_values(["year", "round", "positionOrder"])
    )

    docs: list[Document] = []

    # One document per race, with the full classification (not just the top 10).
    for race_id, race_rows in merged.groupby("raceId", sort=False):
        race_rows = race_rows.sort_values("positionOrder")
        first = race_rows.iloc[0]
        lines = [_classification_line(row) for _, row in race_rows.iterrows()]
        fl_line = _overall_fastest_lap_line(race_rows)
        body = "\n".join(lines)
        if fl_line:
            body = f"{body}\n{fl_line}"

        text = (
            f"{first['year']} {first['race_name']} (Round {first['round']}) "
            f"full race classification ({len(race_rows)} entries):\n"
            f"{body}"
        )
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "year": int(first["year"]),
                    "race": first["race_name"],
                    "round": int(first["round"]),
                },
            )
        )

    last_races = races.loc[races.groupby("year")["round"].idxmax()]
    for _, race in last_races.iterrows():
        season_standings = (
            standings[standings["raceId"] == race["raceId"]]
            .merge(drivers[["driverId", "forename", "surname"]], on="driverId")
            .sort_values("position")
            .head(10)
        )
        if season_standings.empty:
            continue

        lines = []
        for _, s in season_standings.iterrows():
            lines.append(
                f"P{s['positionText']}: {s['forename']} {s['surname']} — "
                f"{_clean(s['points'])} points, {_clean(s['wins'])} wins"
            )

        text = (
            f"{race['year']} Formula 1 World Championship final standings "
            f"(after {race['name']}):\n" + "\n".join(lines)
        )
        docs.append(
            Document(
                page_content=text,
                metadata={"year": int(race["year"]), "type": "championship_standings"},
            )
        )

    return docs


def build_historical_index():
    if not os.path.isdir(DATA_DIR):
        print(f"Error: Historical CSVs not found in '{DATA_DIR}'. Run setup_historical_data.py first.")
        return

    print("Loading embedding model...")
    embeddings = get_embeddings()

    print("Building documents from historical CSVs...")
    documents = build_historical_documents()
    print(f"Generated {len(documents)} historical documents.")

    print("Generating embeddings and FAISS index...")
    vector_db = FAISS.from_documents(documents, embeddings)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    vector_db.save_local(OUTPUT_DIR)
    print(f"Historical index saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    build_historical_index()
