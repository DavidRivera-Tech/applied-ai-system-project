"""Thin Gemini client. Reads GEMINI_API_KEY from the environment or a .env file."""

import os

from dotenv import load_dotenv
from google.genai import types

# Change this one constant to switch models.
MODEL_NAME = "gemini-3.5-flash"
TIMEOUT_MS = 60_000


class LLMError(RuntimeError):
    """Raised with a user-friendly message when the LLM can't be used."""


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
            f"using model '{MODEL_NAME}'. Check your API key, network, quota, and model name."
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
