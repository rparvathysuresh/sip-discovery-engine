"""
Tests for Groq API client in src/utils/groq_client.py.
"""

from unittest.mock import MagicMock, patch
import pytest

from src.utils.groq_client import GroqClient, GroqClientError


def test_groq_client_missing_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(GroqClientError) as exc_info:
        GroqClient(api_key=None)
    assert "Groq API key not provided" in str(exc_info.value)


@patch("src.utils.groq_client.Groq")
def test_groq_client_initialization(mock_groq):
    client = GroqClient(api_key="gsk_test_12345")
    assert client.api_key == "gsk_test_12345"
    assert client.primary_model == "openai/gpt-oss-120b"
    assert client.fallback_model == "openai/gpt-oss-20b"
    mock_groq.assert_called_once_with(api_key="gsk_test_12345")


@patch("src.utils.groq_client.Groq")
def test_groq_client_chat_completion_success(mock_groq):
    mock_groq_instance = MagicMock()
    mock_groq.return_value = mock_groq_instance

    # Mock chat response
    mock_choice = MagicMock()
    mock_choice.message.content = "Test answer"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 12
    mock_usage.completion_tokens = 8
    mock_response = MagicMock(choices=[mock_choice], usage=mock_usage)
    mock_groq_instance.chat.completions.create.return_value = mock_response

    client = GroqClient(api_key="gsk_test_12345")
    res = client.chat_completion([{"role": "user", "content": "Hello"}])

    assert res["content"] == "Test answer"
    assert res["model"] == "openai/gpt-oss-120b"
    assert client.total_requests == 1
    assert client.total_prompt_tokens == 12
    assert client.total_completion_tokens == 8


@patch("src.utils.groq_client.Groq")
def test_groq_client_extract_json(mock_groq):
    mock_groq_instance = MagicMock()
    mock_groq.return_value = mock_groq_instance

    mock_choice = MagicMock()
    mock_choice.message.content = '{"status": "ok", "lifecycle_stage": "months 2 to 3"}'
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 20
    mock_usage.completion_tokens = 15
    mock_response = MagicMock(choices=[mock_choice], usage=mock_usage)
    mock_groq_instance.chat.completions.create.return_value = mock_response

    client = GroqClient(api_key="gsk_test_12345")
    data = client.extract_json([{"role": "user", "content": "Extract tags"}])

    assert isinstance(data, dict)
    assert data["parsed"]["status"] == "ok"
    assert data["parsed"]["lifecycle_stage"] == "months 2 to 3"

