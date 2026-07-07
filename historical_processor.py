import os
import torch
import pandas as pd
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

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
        .merge(constructors[["constructorId", "name"]].rename(columns={"name": "constructor_name"}), on="constructorId")
        .merge(races[["raceId", "year", "round", "name"]].rename(columns={"name": "race_name"}), on="raceId")
    )

    docs: list[Document] = []

    for _, row in merged.iterrows():
        text = (
            f"In the {row['year']} {row['race_name']} (round {row['round']}), "
            f"{row['forename']} {row['surname']} drove for {row['constructor_name']}. "
            f"He finished in position {_clean(row['positionText'])} starting from grid {_clean(row['grid'])}. "
            f"Race time or gap: {_clean(row['time'])}. Points scored: {_clean(row['points'])}. "
            f"Fastest lap: {_clean(row['fastestLapTime'])}."
        )
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "year": int(row["year"]),
                    "race": row["race_name"],
                    "driver": f"{row['forename']} {row['surname']}",
                    "team": row["constructor_name"],
                },
            )
        )

    # Season championship snapshots from the final round of each year
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
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-en-v1.5",
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )

    print("Building documents from historical CSVs...")
    documents = build_historical_documents()
    print(f"Generated {len(documents)} historical documents.")

    print("Generating embeddings and FAISS index (this may take a few minutes)...")
    vector_db = FAISS.from_documents(documents, embeddings)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    vector_db.save_local(OUTPUT_DIR)
    print(f"Historical index saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    build_historical_index()
