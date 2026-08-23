"""Format source citations appended to bot answers."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceCitation:
    kind: str
    label: str

    def format(self) -> str:
        return f"\n\n— Source: {self.label}"


def append_citation(answer: str, source: SourceCitation | None) -> str:
    if source is None:
        return answer
    footer = source.format()
    if footer.strip() in answer:
        return answer
    return answer.rstrip() + footer


def csv_race_results(*, year: int, venue: str | None = None) -> SourceCitation:
    detail = f"{year} {venue}" if venue else str(year)
    return SourceCitation(
        "csv",
        f"Historical CSV (results.csv, races.csv) — {detail}",
    )


def csv_driver_teams(*, year: int) -> SourceCitation:
    return SourceCitation(
        "csv",
        f"Historical CSV (results.csv, drivers.csv, constructors.csv) — {year} season",
    )


def csv_lap_times(*, year: int, venue: str, lap: int | None = None) -> SourceCitation:
    lap_bit = f", lap {lap}" if lap is not None else ""
    return SourceCitation(
        "csv",
        f"Historical CSV (lap_times.csv) — {year} {venue}{lap_bit}",
    )


def csv_top_speed(*, scope: str) -> SourceCitation:
    return SourceCitation(
        "csv",
        f"Historical CSV (results.csv fastestLapSpeed) — {scope}",
    )


def openf1_speed_trap(*, detail: str) -> SourceCitation:
    return SourceCitation("openf1", f"OpenF1 API — speed trap ({detail})")


def speed_trap_records(*, scope: str) -> SourceCitation:
    return SourceCitation("reference", f"Published F1 speed-trap records — {scope}")


def openf1_api(*, endpoint: str, detail: str) -> SourceCitation:
    return SourceCitation("openf1", f"OpenF1 API — {endpoint} ({detail})")


def rag_historical(*, doc_labels: list[str]) -> SourceCitation:
    unique = list(dict.fromkeys(label for label in doc_labels if label))[:3]
    joined = "; ".join(unique) if unique else "historical race documents"
    return SourceCitation("rag", f"Historical vector index — {joined}")


def rag_regulations(*, category: str, year: int, doc_labels: list[str]) -> SourceCitation:
    unique = list(dict.fromkeys(label for label in doc_labels if label))[:3]
    joined = "; ".join(unique) if unique else "regulation PDF"
    return SourceCitation("rag", f"FIA {category} regulations ({year}) — {joined}")


def csv_country_races(*, countries: list[str]) -> SourceCitation:
    joined = ", ".join(countries)
    return SourceCitation(
        "csv",
        f"Historical CSV (races.csv, circuits.csv) — Grands Prix in {joined}",
    )


def multi_gp_venue_map(*, countries: list[str]) -> SourceCitation:
    joined = ", ".join(countries)
    return SourceCitation("reference", f"F1 multi-GP venue map — {joined}")


def conversation_memory() -> SourceCitation:
    return SourceCitation("memory", "Previous answer in this conversation")


def _pdf_label(metadata: dict) -> str:
    src = metadata.get("source", "regulation PDF")
    name = os.path.basename(str(src))
    page = metadata.get("page")
    article = metadata.get("article_id")
    bits = [name]
    if article:
        bits.append(f"Art. {article}")
    if page is not None:
        bits.append(f"p. {int(page) + 1}")
    return ", ".join(bits)


def citation_from_historical_metadata(metadata_list: list[dict]) -> SourceCitation:
    labels: list[str] = []
    for metadata in metadata_list:
        if metadata.get("type") == "championship_standings":
            labels.append(f"{metadata.get('year')} championship standings")
        elif metadata.get("race"):
            labels.append(f"{metadata.get('year')} {metadata.get('race')}")
        else:
            labels.append("historical race document")
    return rag_historical(doc_labels=labels)


def citation_from_regulation_metadata(
    category: str,
    year: int,
    metadata_list: list[dict],
) -> SourceCitation:
    return rag_regulations(
        category=category,
        year=year,
        doc_labels=[_pdf_label(metadata) for metadata in metadata_list],
    )


def venue_label(
    *,
    year: int | None = None,
    country: str | None = None,
    location: str | None = None,
) -> str:
    place = location or country or "Grand Prix"
    if year is None:
        return place
    year_str = str(year)
    if place.startswith(year_str):
        return place
    return f"{year} {place}"
