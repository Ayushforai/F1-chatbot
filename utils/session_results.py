"""Parse user session choices and format session-result offers."""

from __future__ import annotations

OFFERED_SESSIONS = ("Qualifying", "Sprint")

SESSION_ALIASES: dict[str, str] = {
    "qualifying": "Qualifying",
    "quali": "Qualifying",
    "qualifying session": "Qualifying",
    "qualifying results": "Qualifying",
    "grid": "Qualifying",
    "sprint": "Sprint",
    "sprint race": "Sprint",
    "sprint results": "Sprint",
}

DECLINE_REPLIES = {
    "no",
    "nope",
    "nah",
    "skip",
    "continue",
    "no thanks",
    "not now",
    "that's fine",
    "thats fine",
    "all good",
    # User already has race results — treat "race" as declining the Qualifying/Sprint offer.
    "race",
    "the race",
    "race results",
    "just the race",
    "race is fine",
}


def session_results_offer() -> str:
    return (
        "\n\nWould you like results from a different session at this Grand Prix? "
        "Reply with Qualifying or Sprint, or say no to continue."
    )


def parse_session_choice(user_query: str) -> str | None:
    """Return a session name, 'decline', or None if unrecognized."""
    text = user_query.strip().lower()
    if not text:
        return None
    if text in DECLINE_REPLIES:
        return "decline"
    if text in SESSION_ALIASES:
        return SESSION_ALIASES[text]
    for alias, session in SESSION_ALIASES.items():
        if alias in text:
            return session
    return None


def is_session_choice_reply(user_query: str) -> bool:
    return parse_session_choice(user_query) is not None
