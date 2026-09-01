import json
import re
import ollama

from utils.driver_numbers import enrich_telemetry_params
from utils.venues import resolve_venue

MODEL_NAME = "qwen2.5:7b-instruct-q8_0"

VALID_CATEGORIES = [
    "general",
    "sporting",
    "technical",
    "financial",
    "operational",
    "quantitative",
    "historical",
]

CAPABILITIES_MENU = """Here is what I can help with:

• Race results & full classifications — e.g. "Results of Monaco GP 2019"
• Lap times, fastest laps & driver deltas — e.g. "Fastest lap at Silverstone 2024" or "Time delta between Bottas and Stroll on lap 32 of Azerbaijan GP 2017"
• Live telemetry — e.g. "Live telemetry for driver #1" (when a session is live)
• Historical facts — winners, podiums, season standings, past seasons
• General regulations — definitions, entries, governance, championship format
• Sporting rules — penalties, safety car, race procedures
• Technical regulations — engines, aerodynamics, weight, fuel limits
• Financial regulations — cost cap, budget penalties
• Operational rules — power units, testing limits, garage procedures

Include a Grand Prix, driver, year, or rules topic in your question for the best answer."""

AMBIGUOUS_QUERY_PROMPT = (
    "Your question is a bit broad for me to look up reliably. "
    "Please be more specific — mention a Grand Prix, driver, year, or rules topic.\n\n"
    + CAPABILITIES_MENU
)

VAGUE_SINGLE_WORDS = {
    "f1",
    "formula",
    "race",
    "racing",
    "driver",
    "drivers",
    "telemetry",
    "stats",
    "statistics",
    "history",
    "rules",
    "regulations",
    "help",
}

VAGUE_PHRASES = (
    "tell me about f1",
    "tell me about formula",
    "something about f1",
    "about f1",
    "about formula 1",
    "about formula one",
    "f1 stats",
    "race stats",
    "formula 1 stats",
)

# How many prior turns `main()` retains in memory.
CONVERSATION_MEMORY_TURNS = 5
# How many of those turns are injected into router/extractor/generation prompts.
ROUTER_CONTEXT_TURNS = 3
MAX_ANSWER_CHARS_IN_PROMPT = 2500


def _format_history(history: list[dict]) -> str:
    """Format recent conversation turns, including assistant answers, for LLM context."""
    if not history:
        return ""
    lines = []
    for turn in history[-ROUTER_CONTEXT_TURNS:]:
        lines.append(f"User: {turn['query']}")
        if turn.get("category"):
            lines.append(f"  -> Routed to: {turn['category']}")
        answer = turn.get("answer")
        if answer:
            if len(answer) > MAX_ANSWER_CHARS_IN_PROMPT:
                answer = answer[:MAX_ANSWER_CHARS_IN_PROMPT] + "\n... [truncated]"
            lines.append(f"Assistant: {answer}")
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"


def is_capabilities_request(user_query: str) -> bool:
    q = user_query.lower().strip()
    if q in {"?", "help", "help me", "menu", "options"}:
        return True
    hints = (
        "what can you do",
        "what do you do",
        "what can you answer",
        "what can you help",
        "how can you help",
        "show me what you can",
        "capabilities",
        "your capabilities",
    )
    return any(hint in q for hint in hints)


def _looks_like_follow_up(user_query: str, history: list[dict] | None) -> bool:
    if not history:
        return False
    q = user_query.lower().strip()
    if re.search(r"\b((?:19|20)\d{2})\b", user_query) and len(q.split()) <= 4:
        return True
    follow_hints = (
        "what about",
        "how about",
        "and in",
        "same race",
        "this race",
        "that race",
        "who finished",
        "who won",
        "who came",
        "what was",
    )
    return any(hint in q for hint in follow_hints) or len(q.split()) <= 3


def _query_has_specific_topic(user_query: str) -> bool:
    q = user_query.lower()
    if re.search(r"\b((?:19|20)\d{2})\b", user_query):
        return True
    venue = resolve_venue(query=user_query)
    if venue["kind"] in ("ok", "clarify"):
        return True
    if re.search(r"#\s*\d+", user_query):
        return True
    topic_hints = (
        "fastest lap",
        "lap time",
        "lap delta",
        "time delta",
        "telemetry",
        "cost cap",
        "budget cap",
        "engine",
        "aero",
        "aerodynamic",
        "safety car",
        "penalty",
        "dnf",
        "qualifying",
        "pole",
        "standings",
        "championship",
        "who won",
        "results",
        "classification",
        "regulation",
        "section a",
        "general provision",
        "entry application",
        "licence",
        "license",
        "power unit",
        "live data",
        "races are held",
        "races held in",
        "hosted in",
        "which races",
        "what races",
        "grand prix",
        " gp",
        "gp ",
    )
    return any(hint in q for hint in topic_hints)


def is_ambiguous_query(user_query: str, history: list[dict] | None = None) -> bool:
    q = user_query.lower().strip()
    if not q:
        return True
    if is_capabilities_request(user_query):
        return True
    if _looks_like_follow_up(user_query, history):
        return False
    if q in VAGUE_SINGLE_WORDS:
        return True
    if any(phrase in q for phrase in VAGUE_PHRASES):
        return True
    if _query_has_specific_topic(user_query):
        return False
    if len(q.split()) <= 2 and not re.search(r"\b((?:19|20)\d{2})\b", user_query):
        return True
    return False


def ambiguous_query_response(user_query: str) -> str:
    if is_capabilities_request(user_query):
        return CAPABILITIES_MENU
    return AMBIGUOUS_QUERY_PROMPT


def get_ambiguous_query_response(user_query: str, history: list[dict] | None = None) -> str | None:
    if not is_ambiguous_query(user_query, history):
        return None
    return ambiguous_query_response(user_query)


def route_query(user_query: str, history: list[dict] = None) -> str:
    from utils.venues import is_country_race_listing_query

    if is_country_race_listing_query(user_query):
        return "historical"

    valid_categories = VALID_CATEGORIES

    history_context = _format_history(history) if history else ""

    system_prompt = (
        "You are an F1 data routing assistant. Categorize the user's query into exactly ONE "
        "of these categories: general, sporting, technical, financial, operational, quantitative, or historical.\n\n"
        "Rules:\n"
        "- Respond with ONLY the category word in lowercase. Do not add punctuation.\n"
        "- 'historical': Questions about past race results, which team a driver raced for in a specific year, "
        "championship winners, driver standings, podium finishes, or any factual question about a specific past race or season. "
        "Do NOT use historical for top-speed or speed-trap questions — those are quantitative.\n"
        "- 'quantitative': Direct requests for live stats, telemetry, speed, top speed, speed trap, RPMs, gear data, or lap times.\n"
        "- 'general': Section A / general regulatory provisions ONLY — definitions, entries, licences, "
        "championship format, governance. Do NOT use general for country or Grand Prix listing questions.\n"
        "- 'sporting': Penalties, race procedures, safety car rules, sprint format, scrutineering.\n"
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
        print(f" [Router Warning] Unrecognized classification: {classification!r}")
        return "ambiguous"
    except Exception as e:
        print(f"Routing error: {e}")
        return "ambiguous"


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
        '  "year": int or null (null if the user did not mention a season; do not guess),\n'
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

        params = json.loads(raw_text)
    except Exception:
        params = {
            "query_type": "live_telemetry",
            "driver_number": None,
            "driver_name": None,
            "year": None,
            "country": None,
            "location": None,
            "lap_number": None,
        }

    return enrich_telemetry_params(params, user_query)
