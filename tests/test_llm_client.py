"""ask_llm must never leak the API key into its error message. No real API calls."""

import pytest

from src import llm_client

FAKE_KEY = "SECRET-KEY-123"


def test_api_key_not_in_llm_error_message(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(llm_client, "load_dotenv", lambda *a, **k: None)  # don't read a real .env

    def exploding_client(*args, **kwargs):
        # A realistic failure: the SDK/HTTP layer echoes the key back in its message.
        raise Exception(f"request to https://example/v1?key={FAKE_KEY} failed")

    monkeypatch.setattr("google.genai.Client", exploding_client)
    with pytest.raises(llm_client.LLMError) as info:
        llm_client.ask_llm("hello")
    assert FAKE_KEY not in str(info.value)
    assert FAKE_KEY not in repr(info.value)
    assert info.value.__cause__ is None  # raised `from None`, so the original message isn't chained


class _FakeAPIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def test_daily_quota_429_is_not_transient():
    msg = "429 RESOURCE_EXHAUSTED. quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert llm_client._is_transient(_FakeAPIError(429, msg)) is False
    assert llm_client._is_transient(_FakeAPIError(429, "Daily limit reached")) is False


def test_per_minute_429_and_5xx_stay_transient():
    assert llm_client._is_transient(_FakeAPIError(429, "quota exceeded: RequestsPerMinute")) is True
    assert llm_client._is_transient(_FakeAPIError(503, "overloaded")) is True
