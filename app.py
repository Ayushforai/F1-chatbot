import ollama
from utils.router import route_query, extract_telemetry_params
from utils.f1_api import (
    LIVE_DATA_UNAVAILABLE_MESSAGE,
    SESSION_NOT_HELD_MESSAGE,
    get_driver_telemetry,
    get_fastest_lap_of_race,
    get_historical_lap,
)
from utils.vector_store import search as vector_search
from utils.historical_db import get_historical_driver_info
from utils.venues import resolve_venue

MODEL_NAME = 'qwen2.5:7b-instruct-q8_0'

MISSING_DRIVER_MESSAGE = (
    "Which driver are you referring to? Please specify a name "
    "(for example Hamilton or Verstappen) or a car number "
    "(for example #44 or #1) so I can look up the right data."
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
    year = params.get("year") or 2026
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

    if q_type == "fastest_lap" and country:
        print(f" [API Connection] Scanning {year} {country} archives for the fastest lap...")
        telemetry_data = get_fastest_lap_of_race(year, country, driver, location=location)
        if telemetry_data == SESSION_NOT_HELD_MESSAGE:
            return {"kind": "error", "message": SESSION_NOT_HELD_MESSAGE}
        return {"kind": "context", "context": f"Historical Fastest Lap Record: {str(telemetry_data)}"}

    if (q_type == "specific_lap" or lap is not None) and country:
        print(f" [API Connection] Accessing historical archives for {country} {year}, Lap {lap}...")
        telemetry_data = get_historical_lap(year, country, driver, lap, location=location)
        if telemetry_data == SESSION_NOT_HELD_MESSAGE:
            return {"kind": "error", "message": SESSION_NOT_HELD_MESSAGE}
        return {"kind": "context", "context": f"Historical Lap Data Packet: {str(telemetry_data)}"}

    print(f" [API Connection] Querying live OpenF1 data stream for Driver #{driver}...")
    telemetry_data = get_driver_telemetry(driver_number=driver)
    if telemetry_data == LIVE_DATA_UNAVAILABLE_MESSAGE:
        return {"kind": "error", "message": LIVE_DATA_UNAVAILABLE_MESSAGE}
    return {"kind": "context", "context": f"Live telemetry data from vehicle streams: {str(telemetry_data)}"}

def generate_f1_response(user_query: str, context_text: str) -> str:
    system_prompt = (
        "You are an elite Formula 1 expert — part race engineer, part statistician, part historian.\n\n"
        "CRITICAL RULES:\n"
        "1. Answer the user's query using ONLY the information provided in the CONTEXT DATA PACKET below.\n"
        "2. If the CONTEXT DATA PACKET contains a dict or structured record, extract and present the relevant fields clearly and conversationally.\n"
        "3. If the CONTEXT DATA PACKET contains an error message or says the driver did not compete, report that honestly. DO NOT guess or fabricate.\n"
        "4. NEVER invent race results, lap times, or team names not present in the context.\n\n"
        f"CONTEXT DATA PACKET:\n{context_text}"
    )

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

def _historical_context(user_query: str, history: list[dict]) -> str:
    try:
        chunks = vector_search("historical", user_query, k=5)
        return "\n\n".join(chunks)
    except Exception as e:
        print(f" [RAG Warning] Vector search failed ({e}). Falling back to CSV lookup...")
        params = extract_telemetry_params(user_query, history=history)
        venue = resolve_venue(
            country=params.get("country"),
            location=params.get("location"),
            query=user_query,
        )
        year = params.get("year") or 2024
        country = params.get("country")
        location = params.get("location")
        if venue["kind"] == "ok":
            country = venue["country"]
            location = venue["location"]
        elif venue["kind"] == "clarify":
            return venue["message"]
        driver_name = params.get("driver_name") or ""
        historical_data = get_historical_driver_info(year, driver_name, country, location=location)
        return f"Historical Race Record: {historical_data}"


def main():
    print("Initializing Hybrid F1 Race Engineer Pipeline...")
    print(f"\nPit Wall Active [Model: {MODEL_NAME}]. Type 'exit' to close telemetry link.\n")

    conversation_history = []

    while True:
        user_query = input("Engineer Query > ").strip()
        if user_query.lower() in ['exit', 'quit']:
            break
        if not user_query:
            continue

        # 1. Routing Layer (with conversation context)
        category = route_query(user_query, history=conversation_history)
        print(f" [Router] Intent isolated to: {category.upper()}")

        # 2. Branching Execution Paths
        if category == "quantitative":
            print(" [Extractor] Processing query context via Qwen...")
            params = extract_telemetry_params(user_query, history=conversation_history)
            
            print(f" [Debug] Qwen Extracted JSON: {params}")

            result = resolve_quantitative_query(params, user_query=user_query)
            if result["kind"] in ("clarify", "error"):
                print(f"\nResponse:\n{result['message']}\n")
                print("-" * 50)
                conversation_history.append({"query": user_query, "category": category})
                conversation_history = conversation_history[-5:]
                continue
            context = result["context"]

        elif category == "historical":
            venue = resolve_venue(query=user_query)
            if venue["kind"] == "clarify":
                print(f"\nResponse:\n{venue['message']}\n")
                print("-" * 50)
                conversation_history.append({"query": user_query, "category": category})
                conversation_history = conversation_history[-5:]
                continue
            print(" [RAG] Searching historical vector store...")
            context = _historical_context(user_query, conversation_history)

        else:
            print(f" [RAG] Searching {category} vector store...")
            try:
                chunks = vector_search(category, user_query, k=3)
                context = "\n\n".join(chunks)
            except FileNotFoundError as e:
                print(f" [Error] {e}\n")
                continue

        # 3. Text Generation
        answer = generate_f1_response(user_query, context)
        print(f"\nResponse:\n{answer}\n")
        print("-" * 50)

        # 4. Update conversation history (keep last 5 turns)
        conversation_history.append({"query": user_query, "category": category})
        conversation_history = conversation_history[-5:]

if __name__ == "__main__":
    main()