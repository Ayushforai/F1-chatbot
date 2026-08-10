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


def build_historical_documents() -> list[Document]:
    races = pd.read_csv(os.path.join(DATA_DIR, "races.csv"))
    drivers = pd.read_csv(os.path.join(DATA_DIR, "drivers.csv"))
    constructors = pd.read_csv(os.path.join(DATA_DIR, "constructors.csv"))
    results = pd.read_csv(os.path.join(DATA_DIR, "results.csv"))
    standings = pd.read_csv(os.path.join(DATA_DIR, "driver_standings.csv"))

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
        .sort_values(["year", "round", "positionOrder"])
    )

    docs: list[Document] = []

    # One document per race keeps the FAISS index small and retrieval accurate.
    for race_id, race_rows in merged.groupby("raceId", sort=False):
        race_rows = race_rows.sort_values("positionOrder")
        first = race_rows.iloc[0]
        lines = []
        for _, row in race_rows.head(10).iterrows():
            lines.append(
                f"P{_clean(row['positionText'])}: {row['forename']} {row['surname']} "
                f"({row['constructor_name']}) — {_clean(row['time'])}, {_clean(row['points'])} pts"
            )

        text = (
            f"{first['year']} {first['race_name']} (Round {first['round']}) race results:\n"
            + "\n".join(lines)
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
