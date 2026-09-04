"""Unified LLM client for local Ollama and cloud providers (Groq, Gemini, OpenAI, Grok)."""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

# Local default — cloud deploy should set LLM_PROVIDER=gemini|groq|openai|grok
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODELS = {
    "ollama": "qwen2.5:7b-instruct-q8_0",
    "groq": "llama-3.3-70b-versatile",
    # Deploy default: newest free-tier Flash. Override with LLM_MODEL if needed:
    # gemini-3.6-flash | gemini-3.5-flash-lite | gemini-3.1-pro-preview
    "gemini": "gemini-3.8-flash",
    "openai": "gpt-4o-mini",
    "grok": "grok-2-latest",
}

# Tried in order after the primary model when Gemini returns 429/5xx overload.
DEFAULT_GEMINI_FALLBACKS = (
    "gemini-3.6-flash",
    "gemini-2.0-flash",
)

# Transient Google / proxy failures worth retrying.
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}

OPENAI_COMPAT_BASES = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "grok": "https://api.x.ai/v1",
}

API_KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "grok": "XAI_API_KEY",
}


def get_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()


def get_model_name(provider: str | None = None) -> str:
    provider = provider or get_provider()
    explicit = (os.getenv("LLM_MODEL") or "").strip()
    if explicit:
        return explicit
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS[DEFAULT_PROVIDER])


# Back-compat for imports that expect MODEL_NAME
MODEL_NAME = get_model_name()


def active_model_label() -> str:
    provider = get_provider()
    return f"{provider}:{get_model_name(provider)}"


def _api_key(provider: str) -> str:
    env_name = API_KEY_ENV.get(provider)
    if not env_name:
        return ""
    return (os.getenv(env_name) or os.getenv("LLM_API_KEY") or "").strip()


def generate(
    *,
    system: str = "",
    prompt: str,
    options: dict[str, Any] | None = None,
    format: str | None = None,
    model: str | None = None,
) -> dict[str, str]:
    """Return ``{"response": text}`` matching the Ollama generate shape."""
    provider = get_provider()
    model_name = model or get_model_name(provider)
    options = options or {}
    temperature = float(options.get("temperature", 0.1))
    top_p = float(options.get("top_p", 0.9))
    json_mode = format == "json"

    if provider == "ollama":
        return _generate_ollama(
            model=model_name,
            system=system,
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            json_mode=json_mode,
        )
    if provider == "gemini":
        return _generate_gemini(
            model=model_name,
            system=system,
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            json_mode=json_mode,
        )
    if provider in OPENAI_COMPAT_BASES:
        return _generate_openai_compatible(
            provider=provider,
            model=model_name,
            system=system,
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            json_mode=json_mode,
        )
    raise ValueError(
        f"Unsupported LLM_PROVIDER={provider!r}. "
        "Use ollama, gemini, groq, openai, or grok."
    )


def _generate_ollama(
    *,
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    top_p: float,
    json_mode: bool,
) -> dict[str, str]:
    import ollama

    kwargs: dict[str, Any] = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "options": {"temperature": temperature, "top_p": top_p},
    }
    if json_mode:
        kwargs["format"] = "json"
    response = ollama.generate(**kwargs)
    return {"response": response.get("response", "")}


def _retry_attempts() -> int:
    raw = (os.getenv("LLM_RETRY_ATTEMPTS") or "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _gemini_model_chain(primary: str) -> list[str]:
    """Primary model first, then env/default fallbacks (deduped)."""
    env = (os.getenv("GEMINI_FALLBACK_MODELS") or "").strip()
    if env:
        extras = [m.strip() for m in env.split(",") if m.strip()]
    else:
        extras = list(DEFAULT_GEMINI_FALLBACKS)
    chain: list[str] = []
    for name in [primary, *extras]:
        if name and name not in chain:
            chain.append(name)
    return chain


def _post_with_retries(
    *,
    label: str,
    do_post,
    attempts: int | None = None,
) -> Any:
    """Retry transient HTTP failures with exponential backoff."""
    attempts = attempts if attempts is not None else _retry_attempts()
    last_error: Exception | None = None
    for attempt in range(attempts):
        response = do_post()
        if response.status_code < 400:
            return response
        snippet = (response.text or "")[:400]
        err = RuntimeError(f"{label} API error {response.status_code}: {snippet}")
        last_error = err
        if response.status_code not in _RETRYABLE_HTTP or attempt >= attempts - 1:
            raise err
        # 0.8s, 1.6s, 3.2s… — enough for brief Gemini overload spikes
        time.sleep(0.8 * (2**attempt))
    assert last_error is not None
    raise last_error


def _generate_openai_compatible(
    *,
    provider: str,
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    top_p: float,
    json_mode: bool,
) -> dict[str, str]:
    api_key = _api_key(provider)
    if not api_key:
        env_name = API_KEY_ENV[provider]
        raise RuntimeError(
            f"{provider} selected but {env_name} (or LLM_API_KEY) is not set."
        )

    base = os.getenv("LLM_BASE_URL") or OPENAI_COMPAT_BASES[provider]
    url = f"{base.rstrip('/')}/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = _post_with_retries(
        label=provider,
        do_post=lambda: requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        ),
    )
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return {"response": text or ""}


def _gemini_generation_config(
    *,
    model: str,
    temperature: float,
    top_p: float,
    json_mode: bool,
) -> dict[str, Any]:
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "topP": top_p,
    }
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    # Gemini 3.8+ expects a thinking level (LOW|MEDIUM|HIGH). Default LOW for
    # faster / cheaper routing + RAG answers; override with GEMINI_THINKING_LEVEL.
    if model.startswith("gemini-3.8") or model.startswith("gemini-3.7"):
        level = (os.getenv("GEMINI_THINKING_LEVEL") or "LOW").strip().upper()
        if level not in {"LOW", "MEDIUM", "HIGH"}:
            level = "LOW"
        generation_config["thinkingConfig"] = {"thinkingLevel": level}
    return generation_config


def _generate_gemini_once(
    *,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    top_p: float,
    json_mode: bool,
) -> dict[str, str]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": _gemini_generation_config(
            model=model,
            temperature=temperature,
            top_p=top_p,
            json_mode=json_mode,
        ),
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    response = _post_with_retries(
        label="gemini",
        do_post=lambda: requests.post(
            url,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=body,
            timeout=120,
        ),
    )
    data = response.json()
    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    text = "".join(part.get("text", "") for part in parts)
    return {"response": text}


def _generate_gemini(
    *,
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    top_p: float,
    json_mode: bool,
) -> dict[str, str]:
    api_key = _api_key("gemini")
    if not api_key:
        raise RuntimeError("gemini selected but GEMINI_API_KEY (or LLM_API_KEY) is not set.")

    last_error: Exception | None = None
    for candidate in _gemini_model_chain(model):
        try:
            return _generate_gemini_once(
                api_key=api_key,
                model=candidate,
                system=system,
                prompt=prompt,
                temperature=temperature,
                top_p=top_p,
                json_mode=json_mode,
            )
        except RuntimeError as exc:
            last_error = exc
            msg = str(exc)
            # Only fall through to the next model on transient overload / rate limits.
            if not any(f"API error {code}" in msg for code in _RETRYABLE_HTTP):
                raise
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("gemini request failed with no models attempted")


def describe_config() -> dict[str, str]:
    provider = get_provider()
    return {
        "provider": provider,
        "model": get_model_name(provider),
        "label": active_model_label(),
        "has_api_key": "yes" if provider == "ollama" or bool(_api_key(provider)) else "no",
    }
