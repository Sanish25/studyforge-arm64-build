"""Environment configuration and safe failure checks for SCRUM-130."""
import os

def fallback_enabled():
    return os.environ.get("AI_FALLBACK_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}

def require_openai_key():
    if fallback_enabled() and not os.environ.get("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OpenAI fallback is enabled but OPENAI_API_KEY is not set")

def openai_model(feature, default="gpt-4o-mini"):
    feature = feature.upper()
    return os.environ.get(
        f"OPENAI_{feature}_MODEL",
        os.environ.get(f"{feature}_LLM_MODEL", default),
    ).strip()
