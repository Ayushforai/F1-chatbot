from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from utils.terminal_input import read_user_query

import os
import re
from datetime import datetime

import ollama
from utils.router import (
    ambiguous_query_response,
    extract_telemetry_params,
    get_ambiguous_query_response,
    route_query,
    _format_history as format_conversation_history,
)
from utils.f1_api import (
    LIVE_DATA_UNAVAILABLE_MESSAGE,
    SESSION_NOT_HELD_MESSAGE,
    get_driver_telemetry,
    get_fastest_lap_of_race,
    get_historical_lap,
    get_max_speed_trap,
    get_max_speed_trap_season,
)
from utils.vector_store import search_regulations, search_with_metadata, warmup_rag
from utils.citations import (
    SourceCitation,
    append_citation,
    citation_from_historical_metadata,
    citation_from_regulation_metadata,
    conversation_memory,
    csv_country_races,
    csv_driver_teams,
    csv_lap_times,
    csv_race_results,
    multi_gp_venue_map,
    openf1_api,
    openf1_speed_trap,
    speed_trap_records,
    venue_label,
)
from utils.historical_db import (
    format_country_grand_prix_listing_answer,
    format_driver_teams,
    format_lap_time_delta,
    format_race_classification,
    format_top_speed_lookup,
    get_driver_teams,
    get_historical_driver_info,
    get_lap_time_delta,
)
from utils.speed_records import best_speed_trap_record, speed_record_to_packet
from utils.currency import apply_currency_display, get_currency_prompt_rules, refresh_exchange_rates
from utils.venues import (
    MULTI_GP_COUNTRIES,
    countries_in_query,
    format_multi_gp_listing_answer,
    is_country_race_listing_query,
    is_multi_gp_clarification,
    is_multi_gp_listing_query,
    query_introduces_new_country,
    resolve_venue,
    uses_csv_country_race_listing,
)

MODEL_NAME = 'qwen2.5:7b-instruct-q8_0'

DEFAULT_YEAR = 2026
CONVERSATION_MEMORY_TURNS = 5

REGULATION_CATEGORIES = frozenset({"general", "sporting", "technical", "financial", "operational"})

MISSING_YEAR_MESSAGE = (
    "Which season or year are you referring to? "
    "Please specify a year (for example 2024 or 2023)."
)

MISSING_VENUE_MESSAGE = (
    "Please specify which Grand Prix or circuit you mean "
    "(for example Monza, Miami, or Austin)."
)

MISSING_DRIVER_MESSAGE = (
    "Which driver are you referring to? Please specify a name "
    "(for example Hamilton or Verstappen) or a car number "
    "(for example #44 or #1) so I can look up the right data."
)


def query_needs_year(params: dict, user_query: str = "") -> bool:
    """Race or lap lookups need a season; live telemetry does not."""
    q_type = params.get("query_type")
    lap = params.get("lap_number")
    if q_type not in ("fastest_lap", "specific_lap") and lap is None:
        return False
    country = params.get("country")
    location = params.get("location")
    venue = resolve_venue(country=country, location=location, query=user_query)
    return venue["kind"] == "ok" or bool(country)


def resolve_query_year(user_query: str, params: dict, history: list[dict]) -> dict:
    """Resolve season for a quantitative query, asking before defaulting to 2026."""
    explicit = _explicit_year(user_query)
    if explicit is not None:
        return {"kind": "ok", "year": explicit}

    if not query_needs_year(params, user_query):
        return {"kind": "ok", "year": DEFAULT_YEAR}

    for turn in reversed(history):
        if turn.get("year") is not None and turn.get("category") == "quantitative":
            return {"kind": "ok", "year": turn["year"]}

    return {"kind": "clarify", "message": MISSING_YEAR_MESSAGE}


def resolve_race_results_year(user_query: str, history: list[dict]) -> dict:
    """Resolve season for race-result lookups, asking before defaulting to 2026."""
    explicit = _explicit_year(user_query)
    if explicit is not None:
        return {"kind": "ok", "year": explicit}

    for turn in reversed(history):
        if turn.get("year") is not None:
            return {"kind": "ok", "year": turn["year"]}

    return {"kind": "clarify", "message": MISSING_YEAR_MESSAGE}


def resolve_driver_team_year(user_query: str, history: list[dict]) -> dict:
    """Resolve season for driver-team career lookups."""
    return resolve_race_results_year(user_query, history)


def _resolve_pending_year(user_query: str) -> int:
    return _explicit_year(user_query) or DEFAULT_YEAR


def current_regulations_year() -> int:
    return datetime.now().year


def _regulations_rag_context(
    category: str,
    user_query: str,
    year: int,
) -> tuple[str, SourceCitation]:
    print(f" [RAG] Searching {category} regulations for {year}...")
    chunks, metadata = search_regulations(category, user_query, year=year)
    source = citation_from_regulation_metadata(category, year, metadata)
    context = f"Season: {year}\n\n" + "\n\n".join(chunks)
    return context, source


def _csv_race_citation_from_query(
    user_query: str,
    year: int,
    country: str | None = None,
    location: str | None = None,
) -> SourceCitation:
    if country or location:
        return csv_race_results(year=year, venue=venue_label(year=year, country=country, location=location))
    venue = resolve_venue(query=user_query)
    if venue["kind"] == "ok":
        return csv_race_results(
            year=year,
            venue=venue_label(
                year=year,
                country=venue.get("country"),
                location=venue.get("location"),
            ),
        )
    return csv_race_results(year=year)


def _regulations_year_offer(year: int) -> str:
    return (
        f"\n\nThis answer reflects the {year} regulations. "
        "Would you like the same information for a different year? "
        "Reply with a year (for example 2024 or 2022)."
    )


def _is_race_results_query(user_query: str) -> bool:
    """True when the user is asking for full results of a specific Grand Prix."""
    if not _wants_full_classification_or_pace(user_query):
        return False
    venue = resolve_venue(query=user_query)
    return venue["kind"] in ("ok", "clarify")


def _is_year_clarification_reply(user_query: str) -> bool:
    """True when the user is answering a year prompt rather than changing topic."""
    if _explicit_year(user_query) is not None:
        return True
    if not user_query.strip():
        return True
    q = user_query.lower().strip()
    if len(q.split()) <= 3:
        return True
    vague = {
        "yes", "no", "ok", "okay", "sure", "idk", "dunno",
        "don't know", "do not know", "not sure", "any", "whatever", "current",
    }
    return q in vague


def _should_abandon_year_clarification(user_query: str) -> bool:
    """True when the user changed topic instead of answering the year prompt."""
    return not _is_year_clarification_reply(user_query)


def _apply_pending_year_clarification(user_query: str, pending: dict) -> dict:
    """Merge a clarification reply into the pending quantitative params."""
    params = dict(pending["pending_params"])
    params["year"] = _resolve_pending_year(user_query)
    return params


def _format_race_results_response(user_query: str, history: list[dict], year: int) -> str:
    """Look up and format full race results for the given year."""
    venue = resolve_venue(query=user_query)
    if venue["kind"] == "clarify":
        return venue["message"]

    context = _csv_historical_record(user_query, history, year=year)
    if context and is_multi_gp_clarification(context):
        return context
    if context:
        return context
    return (
        f"No race results found in the historical CSV database for "
        f"{year}. Check the Grand Prix name or year and try again."
    )


def _prompt_for_venue(user_query: str, category: str, pending_kind: str, **pending_extra) -> dict:
    """Build a conversation-history entry while waiting for a circuit choice."""
    entry = {
        "query": user_query,
        "category": category,
        "awaiting_venue": True,
        "pending_kind": pending_kind,
        "pending_query": user_query,
    }
    entry.update(pending_extra)
    return entry


def _venue_clarification_message(
    user_query: str,
    country: str | None = None,
    location: str | None = None,
) -> str | None:
    venue = resolve_venue(country=country, location=location, query=user_query)
    if venue["kind"] == "clarify":
        return venue["message"]
    return None


def _resolve_venue_from_clarification(user_query: str, pending: dict) -> dict:
    """Resolve a circuit reply against the original ambiguous query."""
    combined = f"{pending.get('pending_query', '')} {user_query}".strip()
    venue = resolve_venue(query=combined)
    if venue["kind"] == "ok":
        return venue
    return resolve_venue(query=user_query)


def _is_venue_clarification_reply(user_query: str) -> bool:
    if resolve_venue(query=user_query)["kind"] == "ok":
        return True
    if not user_query.strip():
        return True
    q = user_query.lower().strip()
    if len(q.split()) <= 4:
        return True
    return False


def _should_abandon_venue_clarification(user_query: str) -> bool:
    return not _is_venue_clarification_reply(user_query)


def _ask_for_venue_clarification(
    history: list[dict],
    user_query: str,
    category: str,
    pending_kind: str,
    message: str,
    **pending_extra,
) -> None:
    print(f"\nResponse:\n{message}\n")
    print("-" * 50)
    _save_conversation_turn(
        history,
        {
            **_prompt_for_venue(user_query, category, pending_kind, **pending_extra),
            "answer": message,
        },
    )


def _maybe_ask_for_venue(
    history: list[dict],
    user_query: str,
    category: str,
    pending_kind: str,
    country: str | None = None,
    location: str | None = None,
    **pending_extra,
) -> bool:
    """Prompt for a circuit when a multi-GP country is ambiguous. Returns True if prompted."""
    message = _venue_clarification_message(user_query, country=country, location=location)
    if not message:
        return False
    _ask_for_venue_clarification(
        history, user_query, category, pending_kind, message, **pending_extra,
    )
    return True


def _save_conversation_turn(history: list[dict], turn: dict) -> None:
    """Append a turn and keep only the most recent CONVERSATION_MEMORY_TURNS entries."""
    history.append(turn)
    del history[:-CONVERSATION_MEMORY_TURNS]


def _make_turn(user_query: str, category: str, answer: str | None = None, **extra) -> dict:
    turn = {"query": user_query, "category": category}
    if answer is not None:
        turn["answer"] = answer
    turn.update(extra)
    return turn


def _respond_and_remember(
    history: list[dict],
    user_query: str,
    category: str,
    answer: str,
    source: SourceCitation | None = None,
    **extra,
) -> None:
    answer = apply_currency_display(answer, user_query=user_query, category=category)
    answer = append_citation(answer, source)
    print(f"\nResponse:\n{answer}\n")
    print("-" * 50)
    _save_conversation_turn(history, _make_turn(user_query, category, answer, **extra))


LOOKUP_REQUEST_HINTS = (
    "look it up",
    "look up",
    "lookup",
    "look again",
    "check the data",
    "check the database",
    "check csv",
    "use the database",
    "use csv",
    "verify",
    "double check",
    "double-check",
    "confirm",
    "fetch",
    "search for",
    "find out",
    "check again",
    "actually look",
    "don't use memory",
    "do not use memory",
    "re-query",
    "requery",
)


def _is_lap_comparison_query(user_query: str) -> bool:
    q = user_query.lower()
    has_lap = bool(re.search(r"\blap\s+\d+\b", q))
    if not has_lap:
        return False
    hints = (
        "delta",
        "gap",
        "difference",
        "compare",
        "between",
        "vs",
        "versus",
        "slower",
        "faster",
        "lap time",
        "time between",
    )
    return any(hint in q for hint in hints)


def _lap_number_from_query(user_query: str) -> int | None:
    match = re.search(r"\blap\s+(\d+)\b", user_query, re.I)
    return int(match.group(1)) if match else None


def _extract_two_drivers(user_query: str) -> tuple[str, str] | None:
    match = re.search(r"between\s+(\w+)\s+and\s+(\w+)", user_query, re.I)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    match = re.search(r"(\w+)\s+vs\.?\s+(\w+)", user_query, re.I)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None


def _race_context_from_history(history: list[dict]) -> dict | None:
    for turn in reversed(history):
        ctx = _prior_turn_race_context(turn)
        if ctx:
            return ctx
    return None


def _race_context_from_query(user_query: str) -> dict | None:
    """Build race context from an explicit year and venue in the query."""
    year = _explicit_year(user_query)
    if year is None:
        return None
    venue = resolve_venue(query=user_query)
    if venue["kind"] != "ok":
        return None
    return {
        "query": user_query,
        "year": year,
        "country": venue["country"],
        "location": venue.get("location"),
    }


def _resolve_lap_comparison_race_context(user_query: str, history: list[dict]) -> dict | None:
    return _race_context_from_query(user_query) or _race_context_from_history(history)


def _try_lap_comparison_lookup(user_query: str, history: list[dict]) -> str | None:
    """Answer lap-time delta questions from lap_times.csv when possible."""
    if not _is_lap_comparison_query(user_query):
        return None

    lap_number = _lap_number_from_query(user_query)
    drivers = _extract_two_drivers(user_query)
    if lap_number is None or not drivers:
        return None

    race_ctx = _resolve_lap_comparison_race_context(user_query, history)
    if not race_ctx:
        return _venue_clarification_message(user_query)

    print(
        f" [CSV] Looking up lap {lap_number} times for "
        f"{drivers[0]} vs {drivers[1]} in {race_ctx['year']}..."
    )
    result = get_lap_time_delta(
        race_ctx["year"],
        race_ctx["country"],
        drivers[0],
        drivers[1],
        lap_number,
        location=race_ctx.get("location"),
    )
    if isinstance(result, str):
        return result
    return format_lap_time_delta(result)


def _respond_lap_comparison(conversation_history: list[dict], user_query: str) -> bool:
    """Handle lap-delta queries, including multi-GP venue clarification."""
    if not _is_lap_comparison_query(user_query):
        return False

    lap_answer = _try_lap_comparison_lookup(user_query, conversation_history)
    if not lap_answer:
        return False

    if is_multi_gp_clarification(lap_answer):
        drivers = _extract_two_drivers(user_query)
        _maybe_ask_for_venue(
            conversation_history,
            user_query,
            "historical",
            "lap_comparison",
            lap_number=_lap_number_from_query(user_query),
            drivers=list(drivers) if drivers else None,
            year=_explicit_year(user_query),
        )
        return True

    race_ctx = _resolve_lap_comparison_race_context(user_query, conversation_history) or {}
    extra = {}
    if race_ctx.get("year") is not None:
        extra["year"] = race_ctx["year"]
    if race_ctx.get("query"):
        extra["race_lookup_query"] = race_ctx["query"]
    lap_number = _lap_number_from_query(user_query)
    source = csv_lap_times(
        year=race_ctx.get("year") or _explicit_year(user_query) or 0,
        venue=venue_label(
            year=race_ctx.get("year"),
            country=race_ctx.get("country"),
            location=race_ctx.get("location"),
        ),
        lap=lap_number,
    )
    _respond_and_remember(
        conversation_history,
        user_query,
        "historical",
        lap_answer,
        source=source,
        **extra,
    )
    return True


def _user_wants_fresh_lookup(user_query: str) -> bool:
    q = user_query.lower()
    return any(hint in q for hint in LOOKUP_REQUEST_HINTS)


def _looks_like_race_results_answer(answer: str) -> bool:
    text = answer.lower()
    return (
        "grand prix" in text
        or "classified finishers" in text
        or "did not finish" in text
        or bool(re.search(r"(?m)^\d+\.\s+\w", answer))
    )


def _prior_answer_likely_sufficient(user_query: str, prior_answer: str) -> bool:
    """Heuristic check: is the stored answer likely to contain this follow-up fact?"""
    if not prior_answer.strip():
        return False
    if is_country_race_listing_query(user_query):
        return False
    if query_introduces_new_country(user_query, prior_answer):
        return False
    if _user_wants_fresh_lookup(user_query):
        return False

    q = user_query.lower()
    answer = prior_answer.lower()

    if any(key in q for key in ("second", "2nd", "runner-up", "p2")):
        return any(marker in answer for marker in ("2.", "p2", "2nd", " second"))
    if any(key in q for key in ("third", "3rd", "p3")):
        return any(marker in answer for marker in ("3.", "p3", "3rd", " third"))
    if any(key in q for key in ("fourth", "4th", "p4")):
        return any(marker in answer for marker in ("4.", "p4", "4th", " fourth"))
    if "who won" in q or q.strip() in {"winner?", "who won?"}:
        return any(marker in answer for marker in ("1.", "p1", "1st", " winner"))
    if any(key in q for key in ("dnf", "retired", "retirement", "did not finish")):
        return "did not finish" in answer or "retire" in answer or "dnf" in answer
    if "fastest lap" in q and "on lap" not in q:
        return "fastest lap" in answer
    if _is_lap_comparison_query(user_query):
        return False

    if _looks_like_race_results_answer(prior_answer) and len(prior_answer) > 150:
        return True
    return len(prior_answer) > 400


def _prior_turn_driver_team_context(prior: dict) -> dict | None:
    """Recover driver and base query from a prior driver-team lookup turn."""
    query = prior.get("driver_lookup_query") or prior.get("pending_query") or prior.get("query")
    if not query:
        return None
    if not prior.get("driver_lookup_query") and not _is_driver_team_query(query):
        return None
    driver_ref = _driver_ref_from_team_query(query)
    if not driver_ref:
        return None
    return {"query": query, "driver_ref": driver_ref}


def _prior_turn_race_context(prior: dict) -> dict | None:
    """Recover year and venue from a prior race-results turn for re-lookup."""
    query = prior.get("race_lookup_query") or prior.get("pending_query") or prior.get("query")
    if not query:
        return None
    year = prior.get("year") or _explicit_year(query)
    if year is None:
        return None
    venue = resolve_venue(query=query)
    if venue["kind"] != "ok":
        return None
    return {
        "query": query,
        "year": year,
        "country": venue["country"],
        "location": venue["location"],
    }


def _build_follow_up_lookup_context(
    user_query: str,
    history: list[dict],
) -> tuple[str, SourceCitation] | None:
    """Fetch fresh data for a follow-up when memory alone is not enough."""
    if not history:
        return None

    prior = history[-1]
    driver_ctx = _prior_turn_driver_team_context(prior)
    if driver_ctx:
        year = _explicit_year(user_query)
        if year is None:
            year_result = resolve_driver_team_year(user_query, history)
            if year_result["kind"] != "ok":
                return None
            year = year_result["year"]
        print(
            f" [CSV] Driver-team follow-up lookup for {driver_ctx['driver_ref']} in {year}..."
        )
        fresh = _lookup_driver_teams(
            driver_ctx["query"],
            year,
            history=history,
            driver_ref=driver_ctx["driver_ref"],
        )
        return (
            "Use the FRESH LOOKUP DATA below to answer the follow-up.\n\n"
            f"FRESH LOOKUP DATA:\n{fresh}\n\n"
            f"{_follow_up_context(history)}",
            csv_driver_teams(year=year),
        )

    race_ctx = _prior_turn_race_context(prior)
    if race_ctx:
        print(
            f" [Lookup] Re-fetching {race_ctx['year']} race classification "
            f"for follow-up verification..."
        )
        fresh = _format_race_results_response(
            race_ctx["query"], history, race_ctx["year"],
        )
        return (
            "Use the FRESH LOOKUP DATA below to answer the follow-up. "
            "Prefer this data over the previous answer if they disagree.\n\n"
            f"FRESH LOOKUP DATA:\n{fresh}\n\n"
            f"{_follow_up_context(history)}",
            _csv_race_citation_from_query(
                race_ctx["query"],
                race_ctx["year"],
                country=race_ctx.get("country"),
                location=race_ctx.get("location"),
            ),
        )

    if prior.get("category") == "historical":
        print(" [Lookup] Searching historical sources for follow-up...")
        enriched = f"{prior.get('query', '')} {user_query}".strip()
        context, source = _historical_context(enriched, history)
        if context and not context.startswith("No race results found"):
            return (
                "Use the FRESH LOOKUP DATA below to answer the follow-up.\n\n"
                f"FRESH LOOKUP DATA:\n{context}\n\n"
                f"{_follow_up_context(history)}",
                source,
            )

    if prior.get("category") == "quantitative" and prior.get("lookup_params"):
        params = dict(prior["lookup_params"])
        params.update(extract_telemetry_params(user_query, history=history))
        year_result = resolve_query_year(user_query, params, history)
        if year_result["kind"] == "ok":
            params["year"] = year_result["year"]
        result = resolve_quantitative_query(params, user_query=user_query)
        if result["kind"] == "context":
            print(" [Lookup] Re-querying quantitative data for follow-up...")
            return (
                "Use the FRESH LOOKUP DATA below to answer the follow-up.\n\n"
                f"FRESH LOOKUP DATA:\n{result['context']}\n\n"
                f"{_follow_up_context(history)}",
                result["source"],
            )

    return None


def _try_driver_team_follow_up(user_query: str, history: list[dict]) -> dict | None:
    """Answer a year-only follow-up to a driver-team query directly from CSV."""
    if not _is_answer_follow_up(user_query, history):
        return None

    prior = history[-1]
    driver_ctx = _prior_turn_driver_team_context(prior)
    if not driver_ctx:
        return None

    year = _explicit_year(user_query)
    if year is None:
        return None

    answer = _lookup_driver_teams(
        driver_ctx["query"],
        year,
        history=history,
        driver_ref=driver_ctx["driver_ref"],
    )
    return {
        "category": "historical",
        "answer": answer,
        "year": year,
        "driver_lookup_query": driver_ctx["query"],
        "source": csv_driver_teams(year=year),
    }


def _try_answer_follow_up(user_query: str, history: list[dict]) -> dict | None:
    """Answer a follow-up from memory or fresh lookup. Returns None to use normal routing."""
    if not _is_answer_follow_up(user_query, history):
        return None

    driver_follow_up = _try_driver_team_follow_up(user_query, history)
    if driver_follow_up:
        print(" [CSV] Driver-team follow-up answered from CSV lookup")
        return driver_follow_up

    prior = history[-1]
    wants_lookup = _user_wants_fresh_lookup(user_query)
    sufficient = _prior_answer_likely_sufficient(user_query, prior.get("answer", ""))

    category = route_query(user_query, history=history)

    if not wants_lookup and sufficient:
        print(" [Memory] Follow-up answered from previous response")
        answer = generate_f1_response(
            user_query,
            _follow_up_context(history),
            history=history,
        )
        return {"category": category, "answer": answer, "source": conversation_memory()}

    reason = "user requested verification" if wants_lookup else "prior answer insufficient"
    print(f" [Memory] Follow-up needs fresh lookup ({reason})")
    lookup = _build_follow_up_lookup_context(user_query, history)
    if lookup is None:
        return None

    lookup_context, source = lookup
    answer = generate_f1_response(user_query, lookup_context, history=history)
    extra = {}
    driver_ctx = _prior_turn_driver_team_context(prior)
    if driver_ctx:
        year = _explicit_year(user_query) or prior.get("year")
        if year is not None:
            extra["year"] = year
        extra["driver_lookup_query"] = driver_ctx["query"]
    race_ctx = _prior_turn_race_context(prior)
    if race_ctx:
        extra["year"] = race_ctx["year"]
        extra["race_lookup_query"] = race_ctx["query"]
    return {"category": category, "answer": answer, "source": source, **extra}


def _is_answer_follow_up(user_query: str, history: list[dict]) -> bool:
    """True when the user is likely asking about the immediately previous answer."""
    if not history or not history[-1].get("answer"):
        return False
    if is_country_race_listing_query(user_query):
        return False
    prior_answer = history[-1].get("answer", "")
    if query_introduces_new_country(user_query, prior_answer):
        return False
    if _is_race_results_query(user_query):
        return False
    q = user_query.lower().strip()
    follow_hints = (
        "who finished",
        "who came",
        "who was",
        "who won",
        "what about",
        "what was",
        "second",
        "third",
        "fourth",
        "podium",
        "dnf",
        "retired",
        "retirements",
        "and in",
        "and what",
        "how about",
        "tell me more",
        "which driver",
        "who got",
        "fastest lap",
    )
    if any(hint in q for hint in follow_hints):
        return True
    return len(q.split()) <= 8 and q.endswith("?")


def _follow_up_context(history: list[dict]) -> str:
    prior = history[-1]
    return (
        "Answer the follow-up using ONLY the previous exchange below. "
        "Do not invent facts that are not already in the previous answer.\n\n"
        f"PREVIOUS USER QUESTION:\n{prior['query']}\n\n"
        f"PREVIOUS ANSWER:\n{prior['answer']}"
    )


def _has_driver(driver) -> bool:
    """True when the extractor produced a usable driver number."""
    return driver is not None and driver != ""


def query_requires_driver(q_type: str | None, country) -> bool:
    """Overall fastest-lap of a named race does not need a driver; live/lap lookups do."""
    return not (q_type == "fastest_lap" and country)


def resolve_quantitative_query(params: dict, user_query: str = "") -> dict:
    """Build a quantitative reply.

    Returns ``{"kind": "clarify", "message": str}`` when a driver or GP is
    required but missing, ``{"kind": "error", "message": str}`` for known
    failures, or ``{"kind": "context", "context": str}`` for the LLM.
    """
    q_type = params.get("query_type")
    driver = params.get("driver_number")
    year = params.get("year")
    if year is None:
        year = DEFAULT_YEAR
    country = params.get("country")
    location = params.get("location")
    lap = params.get("lap_number")

    is_race_lookup = q_type in ("fastest_lap", "specific_lap") or lap is not None
    if is_race_lookup:
        venue = resolve_venue(country=country, location=location, query=user_query)
        if venue["kind"] == "clarify":
            return {"kind": "clarify", "message": venue["message"]}
        if venue["kind"] == "ok":
            country = venue["country"]
            location = venue["location"]

    if query_requires_driver(q_type, country) and not _has_driver(driver):
        return {"kind": "clarify", "message": MISSING_DRIVER_MESSAGE}

    venue_detail = venue_label(year=year, country=country, location=location)

    if q_type == "fastest_lap" and country:
        print(f" [API Connection] Scanning {year} {country} archives for the fastest lap...")
        telemetry_data = get_fastest_lap_of_race(year, country, driver, location=location)
        if telemetry_data == SESSION_NOT_HELD_MESSAGE:
            return {"kind": "error", "message": SESSION_NOT_HELD_MESSAGE}
        return {
            "kind": "context",
            "context": f"Historical Fastest Lap Record: {str(telemetry_data)}",
            "source": openf1_api(endpoint="fastest lap", detail=venue_detail),
        }

    if (q_type == "specific_lap" or lap is not None) and country:
        print(f" [API Connection] Accessing historical archives for {country} {year}, Lap {lap}...")
        telemetry_data = get_historical_lap(year, country, driver, lap, location=location)
        if telemetry_data == SESSION_NOT_HELD_MESSAGE:
            return {"kind": "error", "message": SESSION_NOT_HELD_MESSAGE}
        return {
            "kind": "context",
            "context": f"Historical Lap Data Packet: {str(telemetry_data)}",
            "source": openf1_api(endpoint=f"lap {lap}", detail=venue_detail),
        }

    print(f" [API Connection] Querying live OpenF1 data stream for Driver #{driver}...")
    telemetry_data = get_driver_telemetry(driver_number=driver)
    if telemetry_data == LIVE_DATA_UNAVAILABLE_MESSAGE:
        return {"kind": "error", "message": LIVE_DATA_UNAVAILABLE_MESSAGE}
    return {
        "kind": "context",
        "context": f"Live telemetry data from vehicle streams: {str(telemetry_data)}",
        "source": openf1_api(endpoint="live telemetry", detail=f"driver #{driver}"),
    }

def generate_f1_response(
    user_query: str,
    context_text: str,
    history: list[dict] | None = None,
    regulation_year: int | None = None,
) -> str:
    history_block = format_conversation_history(history) if history else ""
    system_prompt = (
        "You are an elite Formula 1 expert — part race engineer, part statistician, part historian.\n\n"
        "CRITICAL RULES:\n"
        "1. Answer the user's query using ONLY the information provided in the CONTEXT DATA PACKET below.\n"
        "2. If the CONTEXT DATA PACKET contains a dict or structured record, extract and present the relevant fields clearly and conversationally.\n"
        "3. If the CONTEXT DATA PACKET contains an error message or says the driver did not compete, report that honestly. DO NOT guess or fabricate.\n"
        "4. NEVER invent race results, lap times, or team names not present in the context.\n"
        "5. If the CONTEXT DATA PACKET includes a Classification list or a "
        "'Did not finish' section, list EVERY driver — classified cars AND retirements. "
        "Never stop at the top 10. Never omit DNF/R entries. Never add retirements that are not in the list.\n"
        "6. If RECENT CONVERSATION is provided, use it to interpret follow-up questions.\n"
        f"7. {get_currency_prompt_rules()}\n"
    )
    if regulation_year is not None:
        system_prompt += (
            f"8. Frame the answer as the {regulation_year} season regulations unless the user "
            "explicitly asked about another year.\n"
        )
    system_prompt += f"\n{history_block}CONTEXT DATA PACKET:\n{context_text}"

    try:
        response = ollama.generate(
            model=MODEL_NAME,
            system=system_prompt,
            prompt=user_query,
            options={'temperature': 0.1, 'top_p': 0.9}
        )
        return response['response']
    except Exception as e:
        return f"Telemetry stream interrupted. Error: {e}"


def _has_driver(driver) -> bool:
    """True when the extractor produced a usable driver number."""
    return driver is not None and driver != ""


def _year_from_query(user_query: str, extracted) -> int | None:
    match = re.search(r"\b((?:19|20)\d{2})\b", user_query)
    if match:
        return int(match.group(1))
    return extracted


def _explicit_year(user_query: str) -> int | None:
    if _parse_decade(user_query) is not None:
        return None
    match = re.search(r"\b((?:19|20)\d{2})\b", user_query)
    return int(match.group(1)) if match else None


def _parse_decade(user_query: str) -> tuple[int, int] | None:
    """Parse decades like 2010s or 1990's into (start_year, end_year)."""
    match = re.search(r"\b((?:19|20)(\d{2}))\s*(?:'s|s)\b", user_query, re.I)
    if not match:
        return None
    start = int(match.group(1))
    if start % 10 != 0:
        return None
    return start, start + 9


def _wants_full_classification_or_pace(user_query: str) -> bool:
    """True when the user wants race results, the full grid, DNFs, or fastest-lap detail."""
    q = user_query.lower()
    hints = (
        "result",
        "results",
        "classification",
        "full result",
        "complete result",
        "full classification",
        "complete classification",
        "entire grid",
        "all finishers",
        "full race",
        "complete race",
        "full standings",
        "finishing order",
        "who finished",
        "who won",
        "winner",
        "every driver",
        "fastest lap",
        "quickest lap",
        "lap time",
        "lap times",
        "fastest times",
        "grand prix",
        " gp",
        "gp ",
    )
    return any(hint in q for hint in hints)


def _is_driver_team_query(user_query: str) -> bool:
    """True when the user asks which team a driver raced for in a season."""
    if _wants_full_classification_or_pace(user_query):
        return False
    q = user_query.lower()
    patterns = (
        "which team did",
        "what team did",
        "what team was",
        "who did",
        "drive for",
        "drove for",
        "driving for",
        "'s team",
        " team in 20",
        " team for 20",
    )
    return any(pattern in q for pattern in patterns)


def _driver_ref_from_team_query(user_query: str, history: list[dict] | None = None) -> str | None:
    params = extract_telemetry_params(user_query, history=history or [])
    if params.get("driver_name"):
        return params["driver_name"]

    patterns = [
        r"which team did\s+([A-Za-z\u00C0-\u024F\-']+(?:\s+[A-Za-z\u00C0-\u024F\-']+)?)\s+drive",
        r"what team did\s+([A-Za-z\u00C0-\u024F\-']+(?:\s+[A-Za-z\u00C0-\u024F\-']+)?)\s+drive",
        r"what team was\s+([A-Za-z\u00C0-\u024F\-']+(?:\s+[A-Za-z\u00C0-\u024F\-']+)?)",
        r"([A-Za-z\u00C0-\u024F\-']+(?:\s+[A-Za-z\u00C0-\u024F\-']+)?)'s team",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_query, re.I)
        if match:
            return match.group(1).strip()
    return None


def _lookup_driver_teams(
    user_query: str,
    year: int,
    history: list[dict] | None = None,
    driver_ref: str | None = None,
) -> str:
    if driver_ref is None:
        driver_ref = _driver_ref_from_team_query(user_query, history=history or [])
    if not driver_ref:
        return MISSING_DRIVER_MESSAGE
    print(f" [CSV] Looking up {year} team(s) for {driver_ref}...")
    result = get_driver_teams(year, driver_ref)
    if isinstance(result, str):
        return result
    return format_driver_teams(result)


def _is_top_speed_query(user_query: str) -> bool:
    """True when the user asks about peak or trap speeds."""
    if _is_lap_comparison_query(user_query):
        return False
    q = user_query.lower()
    patterns = (
        "top speed",
        "highest speed",
        "maximum speed",
        "max speed",
        "speed trap",
        "fastest speed",
        "fastest an f1",
        "how fast can",
        "how fast did",
        "ever attained",
        "ever recorded",
        "ever reached",
        "fastest ever",
    )
    return any(pattern in q for pattern in patterns)


def _is_global_top_speed_query(user_query: str) -> bool:
    q = user_query.lower()
    return any(
        phrase in q
        for phrase in (
            "ever attained",
            "ever recorded",
            "ever reached",
            "in history",
            "all time",
            "all-time",
            "has an f1 car",
            "has a f1 car",
            "fastest ever",
        )
    )


def _no_speed_trap_data_message(scope: str) -> str:
    return (
        f"No speed-trap data is available for {scope}. "
        "The historical CSV dataset only includes fastest-lap average speeds "
        "(~240–260 km/h), not peak speed-trap readings. "
        "OpenF1 speed-trap telemetry is available from 2023 onward; "
        "earlier peaks come from published timing records when we have them."
    )


def _lookup_top_speed(
    user_query: str,
    history: list[dict],
    *,
    year: int | None = None,
    venue: dict | None = None,
) -> tuple[str, SourceCitation | None, dict]:
    params = extract_telemetry_params(user_query, history=history)
    decade = _parse_decade(user_query)
    year_start = None
    year_end = None

    if decade is not None:
        year_start, year_end = decade
        year = None
    elif year is None:
        year = _explicit_year(user_query) or params.get("year")
        if year is None:
            for turn in reversed(history):
                if turn.get("year") is not None:
                    year = turn["year"]
                    break

    if venue is None:
        venue = resolve_venue(
            country=params.get("country"),
            location=params.get("location"),
            query=user_query,
        )

    if venue["kind"] == "clarify":
        return venue["message"], None, {}

    driver_number = params.get("driver_number")
    country = venue["country"] if venue["kind"] == "ok" else None
    location = venue.get("location") if venue["kind"] == "ok" else None

    if decade is not None:
        scope_label = f"{year_start}s"
    elif venue["kind"] == "ok":
        scope_label = venue_label(year=year, country=country, location=location)
    elif year is not None:
        scope_label = str(year)
    else:
        scope_label = "all time"

    packets: list[dict] = []
    source: SourceCitation | None = None

    print(f" [Records] Checking published speed-trap records for {scope_label}...")
    published = best_speed_trap_record(
        year=year,
        year_start=year_start,
        year_end=year_end,
        country=country,
        location=location,
    )
    if published:
        packets.append(speed_record_to_packet(published))
        source = speed_trap_records(scope=scope_label)

    trap: dict | str | None = None
    if year is not None and year >= 2023:
        if venue["kind"] == "ok":
            print(f" [API] Scanning {scope_label} for peak speed-trap readings...")
            trap = get_max_speed_trap(
                year,
                country,
                location=location,
                driver_number=driver_number,
            )
        else:
            print(f" [API] Scanning {year} season for peak speed-trap readings...")
            trap = get_max_speed_trap_season(
                year,
                driver_number=driver_number,
            )

    if isinstance(trap, dict):
        if not packets or trap["speed_kmh"] > packets[0]["speed_kmh"]:
            packets.insert(0, trap)
        elif len(packets) == 1:
            pass
        else:
            packets.append(trap)
        source = openf1_speed_trap(detail=trap["race"])
    elif isinstance(trap, str) and not packets:
        if is_multi_gp_clarification(trap):
            return trap, None, {}

    if not packets:
        message = trap if isinstance(trap, str) else _no_speed_trap_data_message(scope_label)
        return message, None, {}

    answer = format_top_speed_lookup(packets, scope=scope_label)
    extra: dict = {"top_speed_query": user_query}
    if year is not None:
        extra["year"] = year
    elif decade is not None:
        extra["year_start"] = year_start
        extra["year_end"] = year_end
    return answer, source, extra


def _handle_top_speed_query(conversation_history: list[dict], user_query: str) -> bool:
    """Answer top-speed / speed-trap questions from OpenF1 and published records."""
    if not _is_top_speed_query(user_query):
        return False

    params = extract_telemetry_params(user_query, history=conversation_history)
    decade = _parse_decade(user_query)
    year = None if decade else (_explicit_year(user_query) or params.get("year"))
    venue = resolve_venue(
        country=params.get("country"),
        location=params.get("location"),
        query=user_query,
    )

    if venue["kind"] == "clarify":
        if _maybe_ask_for_venue(
            conversation_history,
            user_query,
            "quantitative",
            "top_speed",
            year=year,
        ):
            return True

    if (
        decade is None
        and venue["kind"] == "ok"
        and year is None
        and not _is_global_top_speed_query(user_query)
    ):
        year_result = resolve_race_results_year(user_query, conversation_history)
        if year_result["kind"] == "clarify":
            message = year_result["message"]
            print(f"\nResponse:\n{message}\n")
            print("-" * 50)
            _save_conversation_turn(
                conversation_history,
                {
                    **_prompt_for_year(
                        user_query,
                        "quantitative",
                        "top_speed",
                        pending_query=user_query,
                    ),
                    "answer": message,
                },
            )
            return True
        year = year_result["year"]

    answer, source, extra = _lookup_top_speed(
        user_query,
        conversation_history,
        year=year,
        venue=venue,
    )
    if is_multi_gp_clarification(answer):
        _maybe_ask_for_venue(
            conversation_history,
            user_query,
            "quantitative",
            "top_speed",
            year=year,
        )
        return True

    _respond_and_remember(
        conversation_history,
        user_query,
        "quantitative",
        answer,
        source=source,
        **extra,
    )
    return True


def _handle_country_race_listing_query(conversation_history: list[dict], user_query: str) -> bool:
    """Answer questions about which GPs are or were held in a country."""
    if not is_country_race_listing_query(user_query):
        return False

    countries = countries_in_query(user_query)
    if uses_csv_country_race_listing(user_query):
        answer = format_country_grand_prix_listing_answer(user_query, countries)
        if answer is None:
            return False
        print(" [CSV] Looking up Grands Prix by country from historical data...")
        source = csv_country_races(countries=countries)
    else:
        answer = format_multi_gp_listing_answer(user_query)
        if answer is None:
            return False
        countries = [country for country in countries if country in MULTI_GP_COUNTRIES]
        print(" [Venues] Listing multi-GP countries from calendar map...")
        source = multi_gp_venue_map(countries=countries)

    _respond_and_remember(
        conversation_history,
        user_query,
        "historical",
        answer,
        source=source,
        country_race_listing_query=user_query,
    )
    return True


def _handle_multi_gp_listing_query(conversation_history: list[dict], user_query: str) -> bool:
    return _handle_country_race_listing_query(conversation_history, user_query)


def _handle_driver_team_query(conversation_history: list[dict], user_query: str) -> bool:
    """Answer driver-team career questions from CSV. Returns True if handled."""
    if not _is_driver_team_query(user_query):
        return False

    year_result = resolve_driver_team_year(user_query, conversation_history)
    if year_result["kind"] == "clarify":
        message = year_result["message"]
        print(f"\nResponse:\n{message}\n")
        print("-" * 50)
        _save_conversation_turn(
            conversation_history,
            {
                **_prompt_for_year(
                    user_query,
                    "historical",
                    "driver_team",
                    pending_query=user_query,
                ),
                "answer": message,
            },
        )
        return True

    year = year_result["year"]
    driver_ref = _driver_ref_from_team_query(user_query, conversation_history)
    if not driver_ref:
        _respond_and_remember(
            conversation_history,
            user_query,
            "historical",
            MISSING_DRIVER_MESSAGE,
        )
        return True

    answer = _lookup_driver_teams(user_query, year)
    _respond_and_remember(
        conversation_history,
        user_query,
        "historical",
        answer,
        source=csv_driver_teams(year=year),
        year=year,
        driver_lookup_query=user_query,
    )
    return True


def _csv_historical_record(
    user_query: str,
    history: list[dict],
    year: int | None = None,
) -> str | None:
    venue = resolve_venue(query=user_query)
    if venue["kind"] == "clarify":
        return venue["message"]

    if year is None:
        year = _explicit_year(user_query)

    country = None
    location = None
    driver_name = ""

    if venue["kind"] == "ok":
        country = venue["country"]
        location = venue["location"]

    if not country:
        params = extract_telemetry_params(user_query, history=history)
        driver_name = params.get("driver_name") or ""
        venue = resolve_venue(
            country=params.get("country"),
            location=params.get("location"),
            query=user_query,
        )
        if venue["kind"] == "clarify":
            return venue["message"]
        if venue["kind"] == "ok":
            country = venue["country"]
            location = venue["location"]

    if not country or year is None:
        return None

    historical_data = get_historical_driver_info(year, driver_name, country, location=location)
    if isinstance(historical_data, str) and historical_data.startswith("No races found"):
        return None
    if isinstance(historical_data, dict):
        return format_race_classification(historical_data)
    return f"Historical Race Record: {historical_data}"


def _historical_context(user_query: str, history: list[dict]) -> tuple[str, SourceCitation | None]:
    if _is_driver_team_query(user_query):
        year_result = resolve_driver_team_year(user_query, history)
        if year_result["kind"] == "ok":
            year = year_result["year"]
            answer = _lookup_driver_teams(user_query, year)
            print(" [CSV] Using driver-team lookup...")
            return answer, csv_driver_teams(year=year)

    try:
        csv_record = _csv_historical_record(user_query, history)
        if csv_record:
            print(" [CSV] Using full race classification...")
            year = _explicit_year(user_query)
            if year is None:
                for turn in reversed(history):
                    if turn.get("year") is not None:
                        year = turn["year"]
                        break
            source = (
                _csv_race_citation_from_query(user_query, year)
                if year is not None
                else None
            )
            return csv_record, source
    except Exception as e:
        print(f" [CSV Warning] Structured lookup failed ({e}). Falling back to RAG...")

    if _is_race_results_query(user_query) and _explicit_year(user_query) is None:
        return (
            "No race results found in the historical CSV database. "
            "Specify the year in your query and try again.",
            None,
        )

    try:
        print(" [RAG] Searching historical vector store...")
        chunks, metadata = search_with_metadata("historical", user_query, k=5)
        source = citation_from_historical_metadata(metadata)
        return "\n\n".join(chunks), source
    except Exception as e:
        print(f" [RAG Warning] Vector search failed ({e}). Falling back to CSV lookup...")
        csv_record = _csv_historical_record(user_query, history)
        if csv_record:
            year = _explicit_year(user_query)
            source = _csv_race_citation_from_query(user_query, year) if year else None
            return csv_record, source
        return f"Historical Race Record: lookup failed ({e})", None


def _prompt_for_year(user_query: str, category: str, pending_kind: str, **pending_extra) -> dict:
    """Build a conversation-history entry while waiting for the user to name a year."""
    entry = {
        "query": user_query,
        "category": category,
        "awaiting_year": True,
        "pending_kind": pending_kind,
    }
    entry.update(pending_extra)
    return entry


def _handle_venue_clarification_resume(conversation_history: list[dict], user_query: str) -> bool:
    """Resume a query after the user names a circuit within a multi-GP country."""
    pending = conversation_history[-1]
    venue = _resolve_venue_from_clarification(user_query, pending)
    if venue["kind"] == "clarify":
        _ask_for_venue_clarification(
            conversation_history,
            user_query,
            pending.get("category", "historical"),
            pending.get("pending_kind", "historical"),
            venue["message"],
            **{k: v for k, v in pending.items() if k.startswith("pending_") or k in ("year", "lap_number", "drivers")},
        )
        return True

    category = pending.get("category", "historical")
    pending_kind = pending.get("pending_kind", "historical")
    original_query = pending.get("pending_query", user_query)
    enriched_query = f"{original_query} {user_query}".strip()

    if pending_kind == "historical_race":
        year = pending.get("year") or _explicit_year(original_query) or _explicit_year(enriched_query)
        if year is None:
            year_result = resolve_race_results_year(enriched_query, conversation_history)
            if year_result["kind"] == "clarify":
                message = year_result["message"]
                print(f"\nResponse:\n{message}\n")
                print("-" * 50)
                _save_conversation_turn(
                    conversation_history,
                    {
                        **_prompt_for_year(
                            user_query,
                            category,
                            "historical_race",
                            pending_query=enriched_query,
                            country=venue["country"],
                            location=venue.get("location"),
                        ),
                        "answer": message,
                    },
                )
                return True
            year = year_result["year"]

        print(f" [Router] Resuming race-results query after venue clarification")
        print(f" [CSV] Looking up {year} race classification...")
        answer = _format_race_results_response(enriched_query, conversation_history, year)
        _respond_and_remember(
            conversation_history,
            user_query,
            category,
            answer,
            source=_csv_race_citation_from_query(
                enriched_query,
                year,
                country=venue["country"],
                location=venue.get("location"),
            ),
            year=year,
            race_lookup_query=enriched_query,
            country=venue["country"],
            location=venue.get("location"),
        )
        return True

    if pending_kind == "lap_comparison":
        lap_number = pending.get("lap_number")
        drivers = pending.get("drivers")
        year = pending.get("year") or _explicit_year(original_query) or _explicit_year(enriched_query)
        if lap_number is None or not drivers or year is None:
            _respond_and_remember(
                conversation_history,
                user_query,
                category,
                "I still need the year, lap number, and both drivers to compare lap times.",
            )
            return True
        print(
            f" [CSV] Looking up lap {lap_number} times for "
            f"{drivers[0]} vs {drivers[1]} in {year}..."
        )
        result = get_lap_time_delta(
            year,
            venue["country"],
            drivers[0],
            drivers[1],
            lap_number,
            location=venue.get("location"),
        )
        answer = result if isinstance(result, str) else format_lap_time_delta(result)
        _respond_and_remember(
            conversation_history,
            user_query,
            category,
            answer,
            source=csv_lap_times(
                year=year,
                venue=venue_label(
                    year=year,
                    country=venue["country"],
                    location=venue.get("location"),
                ),
                lap=lap_number,
            ),
            year=year,
            race_lookup_query=enriched_query,
            country=venue["country"],
            location=venue.get("location"),
        )
        return True

    if pending_kind == "top_speed":
        original_query = pending.get("pending_query", user_query)
        enriched_query = f"{original_query} {user_query}".strip() if user_query else original_query
        year = pending.get("year") or _explicit_year(enriched_query)
        if year is None:
            year_result = resolve_race_results_year(enriched_query, conversation_history)
            if year_result["kind"] == "clarify":
                message = year_result["message"]
                print(f"\nResponse:\n{message}\n")
                print("-" * 50)
                _save_conversation_turn(
                    conversation_history,
                    {
                        **_prompt_for_year(
                            user_query,
                            category,
                            "top_speed",
                            pending_query=enriched_query,
                            country=venue["country"],
                            location=venue.get("location"),
                        ),
                        "answer": message,
                    },
                )
                return True
            year = year_result["year"]

        print(f" [Router] Resuming top-speed query after venue clarification")
        answer, source, extra = _lookup_top_speed(
            enriched_query,
            conversation_history,
            year=year,
            venue=venue,
        )
        _respond_and_remember(
            conversation_history,
            user_query,
            category,
            answer,
            source=source,
            year=year,
            **extra,
        )
        return True

    if pending_kind == "quantitative":
        params = dict(pending.get("pending_params") or {})
        params["country"] = venue["country"]
        params["location"] = venue.get("location")
        if params.get("year") is None:
            year_result = resolve_query_year(enriched_query, params, conversation_history)
            if year_result["kind"] == "clarify":
                message = year_result["message"]
                print(f"\nResponse:\n{message}\n")
                print("-" * 50)
                _save_conversation_turn(
                    conversation_history,
                    {
                        **_prompt_for_year(
                            user_query,
                            category,
                            "quantitative",
                            pending_params=params,
                            pending_query=enriched_query,
                        ),
                        "answer": message,
                    },
                )
                return True
            params["year"] = year_result["year"]

        print(" [Router] Resuming quantitative query after venue clarification")
        print(f" [Debug] Resumed query after venue clarification: {params}")
        result = resolve_quantitative_query(params, user_query=enriched_query)
        if result["kind"] in ("clarify", "error"):
            if result["kind"] == "clarify" and is_multi_gp_clarification(result["message"]):
                _ask_for_venue_clarification(
                    conversation_history,
                    user_query,
                    category,
                    "quantitative",
                    result["message"],
                    pending_params=params,
                    pending_query=enriched_query,
                )
                return True
            _respond_and_remember(conversation_history, user_query, category, result["message"])
            return True
        answer = generate_f1_response(
            enriched_query, result["context"], history=conversation_history,
        )
        _respond_and_remember(
            conversation_history,
            user_query,
            category,
            answer,
            source=result.get("source"),
            year=params.get("year"),
            lookup_params=params,
        )
        return True

    _respond_and_remember(
        conversation_history,
        user_query,
        category,
        MISSING_VENUE_MESSAGE,
    )
    return True


def _rag_warmup_categories() -> list[str] | None:
    """Optional comma-separated index categories to preload at startup."""
    raw = os.getenv("RAG_WARMUP_CATEGORIES", "").strip()
    if not raw:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def main():
    print("Initializing Hybrid F1 Race Engineer Pipeline...")
    rates = refresh_exchange_rates()
    if rates["source"].startswith("live"):
        print(
            f" [FX] Live rates loaded: 1 USD = {rates['usd_to_inr']:.2f} INR, "
            f"1 USD = {rates['usd_to_gbp']:.2f} GBP"
        )
    else:
        print(
            f" [FX] Using fallback rates: 1 USD = {rates['usd_to_inr']:.2f} INR, "
            f"1 USD = {rates['usd_to_gbp']:.2f} GBP"
        )
    print(" [RAG] Loading embedding model into memory...")
    warmup_rag(categories=_rag_warmup_categories())
    print(" [RAG] Embedding model ready.")
    print(f"\nPit Wall Active [Model: {MODEL_NAME}]. Type 'exit' to close telemetry link.\n")

    conversation_history = []

    while True:
        user_query = read_user_query("Engineer Query > ")
        if user_query.lower() in ['exit', 'quit']:
            break
        awaiting_year = conversation_history and conversation_history[-1].get("awaiting_year")
        awaiting_venue = conversation_history and conversation_history[-1].get("awaiting_venue")
        if not user_query and not awaiting_year and not awaiting_venue:
            continue

        history_extra: dict = {}

        if awaiting_venue and not _should_abandon_venue_clarification(user_query):
            _handle_venue_clarification_resume(conversation_history, user_query)
            continue

        if not awaiting_year and not awaiting_venue and _respond_lap_comparison(conversation_history, user_query):
            continue

        if not awaiting_year and not awaiting_venue and _handle_top_speed_query(conversation_history, user_query):
            continue

        if not awaiting_year and not awaiting_venue and _handle_driver_team_query(conversation_history, user_query):
            continue

        if not awaiting_year and not awaiting_venue and _handle_country_race_listing_query(
            conversation_history, user_query
        ):
            continue

        if (
            not awaiting_year
            and not awaiting_venue
            and (ambiguous_answer := get_ambiguous_query_response(user_query, conversation_history))
        ):
            print(" [Router] Query too ambiguous — prompting for specificity")
            _respond_and_remember(
                conversation_history,
                user_query,
                "help",
                ambiguous_answer,
            )
            continue

        if (
            not awaiting_year
            and not awaiting_venue
            and (follow_up := _try_answer_follow_up(user_query, conversation_history))
        ):
            print(f" [Router] Intent isolated to: {follow_up['category'].upper()}")
            _respond_and_remember(
                conversation_history,
                user_query,
                follow_up["category"],
                follow_up["answer"],
                source=follow_up.get("source"),
                **{k: v for k, v in follow_up.items() if k not in ("category", "answer", "source")},
            )
            continue

        # 1. Routing Layer (with conversation context)
        if awaiting_year and not _should_abandon_year_clarification(user_query):
            pending = conversation_history[-1]
            pending_kind = pending.get("pending_kind", "quantitative")
            category = pending.get("category", "quantitative")
            year = _resolve_pending_year(user_query)
            history_extra["year"] = year

            if pending_kind == "historical_race":
                print(" [Router] Resuming race-results query after year clarification")
                original_query = pending["pending_query"]
                if _maybe_ask_for_venue(
                    conversation_history,
                    original_query,
                    category,
                    "historical_race",
                    year=year,
                ):
                    continue
                print(f" [CSV] Looking up {year} race classification...")
                answer = _format_race_results_response(original_query, conversation_history, year)
                if is_multi_gp_clarification(answer):
                    _ask_for_venue_clarification(
                        conversation_history,
                        user_query,
                        category,
                        "historical_race",
                        answer,
                        year=year,
                    )
                    continue
                _respond_and_remember(
                    conversation_history, user_query, "historical", answer,
                    source=_csv_race_citation_from_query(original_query, year),
                    year=year, race_lookup_query=original_query,
                )
                continue

            if pending_kind == "driver_team":
                print(" [Router] Resuming driver-team query after year clarification")
                original_query = pending["pending_query"]
                driver_ref = _driver_ref_from_team_query(original_query, conversation_history)
                if not driver_ref:
                    _respond_and_remember(
                        conversation_history,
                        user_query,
                        category,
                        MISSING_DRIVER_MESSAGE,
                    )
                    continue
                answer = _lookup_driver_teams(original_query, year)
                _respond_and_remember(
                    conversation_history,
                    user_query,
                    category,
                    answer,
                    source=csv_driver_teams(year=year),
                    year=year,
                    driver_lookup_query=original_query,
                )
                continue

            if pending_kind == "top_speed":
                print(" [Router] Resuming top-speed query after year clarification")
                original_query = pending["pending_query"]
                answer, source, extra = _lookup_top_speed(
                    original_query,
                    conversation_history,
                    year=year,
                )
                _respond_and_remember(
                    conversation_history,
                    user_query,
                    category,
                    answer,
                    source=source,
                    year=year,
                    **extra,
                )
                continue

            if pending_kind == "regulations":
                print(" [Router] Resuming regulations query after year clarification")
                original_query = pending["pending_query"]
                try:
                    context, source = _regulations_rag_context(category, original_query, year)
                except FileNotFoundError as e:
                    print(f" [Error] {e}\n")
                    continue
                answer = generate_f1_response(
                    original_query,
                    context,
                    history=conversation_history,
                    regulation_year=year,
                )
                _respond_and_remember(
                    conversation_history,
                    user_query,
                    category,
                    answer,
                    source=source,
                    year=year,
                    pending_query=original_query,
                )
                continue

            print(" [Router] Resuming quantitative query after year clarification")
            params = _apply_pending_year_clarification(user_query, pending)
            print(f" [Debug] Resumed query after year clarification: {params}")
            result = resolve_quantitative_query(params, user_query=user_query)
            if result["kind"] == "clarify" and is_multi_gp_clarification(result["message"]):
                _ask_for_venue_clarification(
                    conversation_history,
                    user_query,
                    category,
                    "quantitative",
                    result["message"],
                    pending_params=params,
                )
                continue
            if result["kind"] in ("clarify", "error"):
                _respond_and_remember(
                    conversation_history, user_query, category, result["message"],
                )
                continue
            answer = generate_f1_response(
                user_query, result["context"], history=conversation_history,
            )
            _respond_and_remember(
                conversation_history, user_query, category, answer,
                source=result.get("source"),
                year=year, lookup_params=params,
            )
            continue

        category = route_query(user_query, history=conversation_history)
        print(f" [Router] Intent isolated to: {category.upper()}")

        if category == "ambiguous":
            answer = get_ambiguous_query_response(user_query, conversation_history) or ambiguous_query_response(user_query)
            _respond_and_remember(
                conversation_history,
                user_query,
                "help",
                answer,
            )
            continue

        if not awaiting_year and not awaiting_venue and _respond_lap_comparison(conversation_history, user_query):
            continue

        # 2. Branching Execution Paths
        offer_other_year = False
        reg_year: int | None = None
        source: SourceCitation | None = None
        context = ""

        if category == "quantitative":
            print(" [Extractor] Processing query context via Qwen...")
            params = extract_telemetry_params(user_query, history=conversation_history)

            print(f" [Debug] Qwen Extracted JSON: {params}")

            year_result = resolve_query_year(user_query, params, conversation_history)
            if year_result["kind"] == "clarify":
                message = year_result["message"]
                print(f"\nResponse:\n{message}\n")
                print("-" * 50)
                _save_conversation_turn(
                    conversation_history,
                    {
                        **_prompt_for_year(
                            user_query, category, "quantitative", pending_params=params,
                        ),
                        "answer": message,
                    },
                )
                continue

            params["year"] = year_result["year"]
            history_extra["year"] = params["year"]
            result = resolve_quantitative_query(params, user_query=user_query)
            if result["kind"] == "clarify" and is_multi_gp_clarification(result["message"]):
                _ask_for_venue_clarification(
                    conversation_history,
                    user_query,
                    category,
                    "quantitative",
                    result["message"],
                    pending_params=params,
                )
                continue
            if result["kind"] in ("clarify", "error"):
                _respond_and_remember(
                    conversation_history, user_query, category, result["message"],
                )
                continue
            context = result["context"]
            source = result.get("source")

        elif category == "historical":
            pending_kind = "historical_race" if _is_race_results_query(user_query) else "historical"
            if _maybe_ask_for_venue(
                conversation_history,
                user_query,
                category,
                pending_kind,
            ):
                continue

            if _is_race_results_query(user_query):
                year_result = resolve_race_results_year(user_query, conversation_history)
                if year_result["kind"] == "clarify":
                    message = year_result["message"]
                    print(f"\nResponse:\n{message}\n")
                    print("-" * 50)
                    _save_conversation_turn(
                        conversation_history,
                        {
                            **_prompt_for_year(
                                user_query, category, "historical_race", pending_query=user_query,
                            ),
                            "answer": message,
                        },
                    )
                    continue

                year = year_result["year"]
                history_extra["year"] = year
                print(f" [CSV] Looking up {year} race classification...")
                answer = _format_race_results_response(
                    user_query, conversation_history, year,
                )
                _respond_and_remember(
                    conversation_history, user_query, category, answer,
                    source=_csv_race_citation_from_query(user_query, year),
                    year=year, race_lookup_query=user_query,
                )
                continue

            print(" [History] Resolving race results...")
            context, source = _historical_context(user_query, conversation_history)

        else:
            reg_year = _explicit_year(user_query)
            offer_other_year = reg_year is None
            if reg_year is None:
                reg_year = current_regulations_year()
            history_extra["year"] = reg_year
            try:
                context, source = _regulations_rag_context(category, user_query, reg_year)
            except FileNotFoundError as e:
                print(f" [Error] {e}\n")
                continue

        # 3. Text Generation
        reg_answer_year = history_extra.get("year") if category in REGULATION_CATEGORIES else None
        answer = generate_f1_response(
            user_query,
            context,
            history=conversation_history,
            regulation_year=reg_answer_year,
        )
        extra = dict(history_extra)
        if category == "quantitative":
            extra["lookup_params"] = params
        if category in REGULATION_CATEGORIES and offer_other_year:
            answer += _regulations_year_offer(reg_year)
            extra["awaiting_year"] = True
            extra["pending_kind"] = "regulations"
            extra["pending_query"] = user_query
        _respond_and_remember(
            conversation_history, user_query, category, answer, source=source, **extra,
        )

if __name__ == "__main__":
    main()