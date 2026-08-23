"""Published F1 speed-trap records not available in Ergast CSV or pre-2023 OpenF1."""

from __future__ import annotations

# Peak speed-trap readings from official timing / widely cited F1 sources.
# Ergast fastestLapSpeed is an average speed on the fastest lap (~240–260 km/h),
# not the speed-trap peaks that reach 350+ km/h on low-downforce circuits.
SPEED_TRAP_RECORDS: list[dict] = [
    {
        "speed_kmh": 378.0,
        "driver": "Valtteri Bottas",
        "team": "Williams",
        "year": 2016,
        "grand_prix": "European Grand Prix",
        "location": "Baku",
        "session": "Qualifying",
    },
]


def best_speed_trap_record(
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    year: int | None = None,
    country: str | None = None,
    location: str | None = None,
) -> dict | None:
    """Return the highest published speed-trap record matching the scope."""
    candidates = SPEED_TRAP_RECORDS

    if year is not None:
        candidates = [record for record in candidates if record["year"] == year]
    else:
        if year_start is not None:
            candidates = [record for record in candidates if record["year"] >= year_start]
        if year_end is not None:
            candidates = [record for record in candidates if record["year"] <= year_end]

    if country or location:
        filtered: list[dict] = []
        scope = f"{location or ''} {country or ''}".lower()
        for record in candidates:
            haystack = " ".join(
                str(record.get(key, ""))
                for key in ("location", "grand_prix", "country")
            ).lower()
            if location and location.lower() in haystack:
                filtered.append(record)
            elif country and country.lower() in haystack:
                filtered.append(record)
            elif location and location.lower() in scope and location.lower() in haystack:
                filtered.append(record)
        candidates = filtered

    if not candidates:
        return None

    return max(candidates, key=lambda record: record["speed_kmh"])


def speed_record_to_packet(record: dict) -> dict:
    session = record.get("session")
    team = record.get("team")
    label = f"{record['year']} {record['grand_prix']}"
    if record.get("location"):
        label = f"{label}, {record['location']}"
    if session:
        label = f"{label} ({session})"
    return {
        "measurement": "published speed-trap record",
        "speed_kmh": float(record["speed_kmh"]),
        "driver": record["driver"],
        "year": int(record["year"]),
        "grand_prix": record["grand_prix"],
        "race": label,
        "session": session,
        "team": team,
        "speed_field_label": "speed trap",
    }
