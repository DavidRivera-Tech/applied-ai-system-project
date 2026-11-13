"""Thin Gemini client. Reads GEMINI_API_KEY from the environment or a .env file."""

import os

from dotenv import load_dotenv
from google.genai import types

# Change this one constant to switch models.
MODEL_NAME = "gemini-3.5-flash"
TIMEOUT_MS = 60_000


class LLMError(RuntimeError):
    """Raised with a user-friendly message when the LLM can't be used.

    `transient` is True for errors worth one retry (timeouts, 429, 5xx, connection drops).
    """

    def __init__(self, message: str, code=None, transient: bool = False):
        super().__init__(message)
        self.code = code
        self.transient = transient


_DAILY_QUOTA_HINTS = ("perday", "per day", "per-day", "daily")


def _is_daily_quota(exc: Exception) -> bool:
    """True if the error text mentions a per-day quota. Read only to classify; never shown or logged."""
    text = str(exc).lower()
    return any(hint in text for hint in _DAILY_QUOTA_HINTS)


def _is_transient(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        if code == 429 and _is_daily_quota(exc):
            return False  # a daily quota won't recover in seconds, so a retry would be wasted
        return code in (408, 429) or 500 <= code < 600
    name = type(exc).__name__.lower()
    return any(word in name for word in ("timeout", "connect", "remote", "network"))


def is_llm_available() -> bool:
    """True only if GEMINI_API_KEY is set (after loading .env)."""
    load_dotenv()
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def ask_llm(prompt: str) -> str:
    """Send a prompt to Gemini and return the response text."""
    if not is_llm_available():
        raise LLMError(
            "GEMINI_API_KEY is not set. Add it to a .env file "
            "(GEMINI_API_KEY=your_key) or set it as an environment variable."
        )
    try:
        from google import genai

        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"].strip(),
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        text = response.text
    except Exception as exc:  # deliberately broad: surface a clean message
        # Only the exception type/message is shown; the key is never included.
        raise LLMError(
            f"Gemini API call failed ({type(exc).__name__}, code={getattr(exc, 'code', 'n/a')}) "
            f"using model '{MODEL_NAME}'. Check your API key, network, quota, and model name.",
            code=getattr(exc, "code", None),
            transient=_is_transient(exc),
        ) from None
    if not text:
        raise LLMError(f"Gemini returned an empty response from model '{MODEL_NAME}'.")
    return text.strip()


if __name__ == "__main__":
    available = is_llm_available()
    print(f"LLM available: {available}")
    if available:
        try:
            print(ask_llm("Reply with exactly: connection ok"))
        except LLMError as err:
            print(f"Error: {err}")
