import json
import re
import ollama

MODEL_NAME = "qwen2.5:7b-instruct-q8_0"


def _format_history(history: list[dict]) -> str:
    """Format recent conversation turns into a string for LLM context."""
    if not history:
        return ""
    lines = []
    for turn in history[-3:]:
        lines.append(f"User: {turn['query']}")
        if turn.get("category"):
            lines.append(f"  -> Routed to: {turn['category']}")
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"


def route_query(user_query: str, history: list[dict] = None) -> str:
    valid_categories = ["sporting", "technical", "financial", "operational", "quantitative", "historical"]

    history_context = _format_history(history) if history else ""

    system_prompt = (
        "You are an F1 data routing assistant. Categorize the user's query into exactly ONE "
        "of these categories: sporting, technical, financial, operational, quantitative, or historical.\n\n"
        "Rules:\n"
        "- Respond with ONLY the category word in lowercase. Do not add punctuation.\n"
        "- 'historical': Questions about past race results, which team a driver raced for in a specific year, "
        "championship winners, driver standings, podium finishes, or any factual question about a specific past race or season.\n"
        "- 'quantitative': Direct requests for live stats, telemetry, speed, RPMs, gear data, or lap times.\n"
        "- 'sporting': Current-season grid positions, penalties, race procedures, safety car rules.\n"
        "- 'technical': Engine specifications, aerodynamics, weight, wings, fuel limits.\n"
        "- 'financial': Cost cap, team spending, budget penalties.\n"
        "- 'operational': Power unit allocation limits, team testing limits, garage rules.\n\n"
        "IMPORTANT: If the user asks a follow-up question (e.g. 'and in 2026?', 'what about Max?'), "
        "use the conversation history to understand the intent. A follow-up to a historical query is still historical.\n"
    )

    prompt_with_context = history_context + f"Current query: {user_query}"

    try:
        response = ollama.generate(
            model=MODEL_NAME,
            system=system_prompt,
            prompt=prompt_with_context,
            options={"temperature": 0.0, "top_p": 0.1},
        )
        classification = response["response"].strip().lower()

        for category in valid_categories:
            if category in classification:
                return category
        return "sporting"
    except Exception as e:
        print(f"Routing error: {e}")
        return "sporting"


def extract_telemetry_params(user_query: str, history: list[dict] = None) -> dict:
    """Extract structured telemetry arguments from natural language, using conversation history for follow-ups."""
    history_context = _format_history(history) if history else ""

    system_prompt = (
        "You are an expert F1 data extraction assistant. Extract parameters from the prompt.\n"
        "Output strictly valid JSON matching this schema:\n"
        "{\n"
        '  "query_type": string ("fastest_lap", "specific_lap", "live_telemetry", or "historical_info"),\n'
        '  "driver_number": int or null (Map names: Lewis/Hamilton=44, Max/Verstappen=1, Lando/Norris=4, Charles/Leclerc=16, Carlos/Sainz=55, Oscar/Piastri=81, George/Russell=63, etc.),\n'
        '  "driver_name": string or null (the driver surname only, e.g. "Hamilton", "Verstappen", "Norris". Extract from the query.),\n'
        '  "year": int (default to 2026 if not mentioned, but use the year explicitly stated in the query),\n'
        '  "country": string or null (OpenF1 country_name: United Kingdom, United Arab Emirates, Italy, United States, Monaco, ...),\n'
        '  "location": string or null (circuit or city when known, e.g. "Monza", "Imola", "Miami", "Austin", "Las Vegas", "Silverstone"),\n'
        '  "lap_number": int or null\n'
        "}\n\n"
        "CRITICAL rules for 'country' and 'location':\n"
        "- Map Grand Prix names to the OpenF1 country_name (NOT informal synonyms):\n"
        '  "British Grand Prix" / Silverstone / UK / Great Britain -> country="United Kingdom", location="Silverstone",\n'
        '  "Abu Dhabi Grand Prix" / Yas Marina -> country="United Arab Emirates", location="Yas Island",\n'
        '  "Italian Grand Prix" / Monza -> country="Italy", location="Monza",\n'
        '  "Emilia Romagna Grand Prix" / Imola -> country="Italy", location="Imola",\n'
        '  "Miami Grand Prix" -> country="United States", location="Miami",\n'
        '  "United States Grand Prix" / Austin / COTA -> country="United States", location="Austin",\n'
        '  "Las Vegas Grand Prix" -> country="United States", location="Las Vegas",\n'
        '  "Monaco Grand Prix" -> country="Monaco", "Spanish Grand Prix" -> country="Spain",\n'
        '  "Belgian Grand Prix" -> country="Belgium", "Dutch Grand Prix" -> country="Netherlands",\n'
        '  "Brazilian Grand Prix" / Sao Paulo -> country="Brazil", "Mexican Grand Prix" -> country="Mexico".\n'
        "- If the user only says Italy or United States / USA without naming the race or circuit, still set country but leave location null.\n"
        "- The country must NEVER be null if a Grand Prix or location is mentioned.\n\n"
        "IMPORTANT: If the user asks a follow-up (e.g. 'and in 2026?', 'what about Max?'), "
        "inherit missing parameters from the conversation history. Only override fields the user explicitly changes.\n"
        "For historical questions about teams, use query_type='historical_info'.\n"
    )

    prompt_with_context = history_context + f"Current query: {user_query}"

    try:
        response = ollama.generate(
            model=MODEL_NAME,
            system=system_prompt,
            prompt=prompt_with_context,
            options={"temperature": 0.0},
            format="json",
        )

        raw_text = response["response"].strip()

        # Strip markdown code fences if the LLM hallucinated them
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()

        return json.loads(raw_text)
    except Exception:
        return {"query_type": "live_telemetry", "driver_number": None, "year": 2026, "country": None, "location": None, "lap_number": None}
