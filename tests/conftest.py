"""Shared test setup: no test may ever reach the real Gemini API."""

import pytest


@pytest.fixture(autouse=True)
def no_live_gemini(monkeypatch):
    """Make the real Gemini client unavailable in every test.

    - GEMINI_API_KEY is blanked, and load_dotenv is turned into a no-op so a real .env cannot put it back.
    - is_llm_available reports False everywhere it is used.
    - The SDK client itself raises, as a last safety net.

    Tests that need a fake LLM still work: they patch is_llm_available / ask_llm themselves,
    and that happens after this fixture runs.
    """
    import google.genai
    from src import assistant, llm_client, profile_parser

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(llm_client, "load_dotenv", lambda *a, **k: None)
    for module in (llm_client, assistant, profile_parser):
        monkeypatch.setattr(module, "is_llm_available", lambda: False)

    def blocked(*args, **kwargs):
        raise RuntimeError("Tests must not call the live Gemini API.")

    monkeypatch.setattr(google.genai, "Client", blocked)
