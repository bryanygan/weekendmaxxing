"""Phase 1 tests — LLM utility layer."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from utils.json_extractor import extract_json
from utils.llm import call_llm


# ── call_llm tests ──────────────────────────────────────────────────────────


def test_call_llm_returns_string():
    """Hit the real Ollama instance and verify we get a non-empty string back."""
    result = call_llm(
        system_prompt="You are a test bot.",
        user_prompt="Reply with the single word PONG and nothing else.",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_call_llm_retry_on_failure():
    """Mock requests.post to fail twice then succeed; verify 3 total calls."""
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.text = "Internal Server Error"

    success_response = MagicMock()
    success_response.status_code = 200
    success_response.json.return_value = {
        "message": {"content": "PONG"}
    }

    with patch("utils.llm.requests.post", side_effect=[fail_response, fail_response, success_response]) as mock_post, \
         patch("utils.llm.time.sleep"):  # skip real sleeps
        result = call_llm("system", "say PONG")

    assert result == "PONG"
    assert mock_post.call_count == 3


# ── extract_json tests ──────────────────────────────────────────────────────


def test_extract_clean_json():
    raw = json.dumps([{"city": "Miami", "price": 120}])
    result = extract_json(raw)
    assert result == [{"city": "Miami", "price": 120}]


def test_extract_fenced_json():
    raw = '```json\n[{"city": "Boston", "price": 99}]\n```'
    result = extract_json(raw)
    assert result == [{"city": "Boston", "price": 99}]


def test_extract_embedded_json():
    raw = 'Here are the results:\n[{"city": "Atlanta"}]\nHope that helps!'
    result = extract_json(raw)
    assert result == [{"city": "Atlanta"}]


def test_extract_invalid_returns_empty():
    result = extract_json("this is not json at all")
    assert result == []


def test_extract_object():
    raw = json.dumps({"origin": "PHL", "budget": 500})
    result = extract_json(raw)
    assert isinstance(result, dict)
    assert result["origin"] == "PHL"
