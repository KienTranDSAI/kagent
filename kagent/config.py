import os
from pathlib import Path
from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env in precedence (high → low):
      1. Real env vars (untouched — system already set).
      2. ./.env (cwd) — dev mode when running from repo.
      3. ~/.kagent/.env — user config, used when installed globally.
    """
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=False)

    user_env = Path.home() / ".kagent" / ".env"
    if user_env.is_file():
        load_dotenv(user_env, override=False)


_load_env()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_VERIFY_SSL = os.getenv("OPENAI_VERIFY_SSL", "true").lower() != "false"

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "claude": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
}


def get_model():
    return LLM_MODEL or DEFAULT_MODELS.get(LLM_PROVIDER, "gemini-2.5-flash")


def get_api_key():
    keys = {
        "gemini": GEMINI_API_KEY,
        "claude": ANTHROPIC_API_KEY,
        "openai": OPENAI_API_KEY,
    }
    return keys.get(LLM_PROVIDER, "")
