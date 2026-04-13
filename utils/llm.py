"""LLM client — calls a local Ollama instance via the /api/chat endpoint."""

import time

import requests

from config import settings


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 1000) -> str:
    """Send a chat completion request to the local LLM and return the response text.

    Retries up to 3 total attempts with a 2-second backoff between failures.
    Raises RuntimeError on non-200 responses or malformed JSON.
    """
    payload = {
        "model": settings.LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }

    last_error: Exception | None = None

    for attempt in range(1, 4):
        start = time.time()
        try:
            print(f"[LLM] prompt: {user_prompt[:80]!r} (attempt {attempt})")
            resp = requests.post(settings.LOCAL_LLM_URL, json=payload, timeout=120)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2)
            continue

        elapsed = time.time() - start
        print(f"[LLM] responded in {elapsed:.2f}s (status {resp.status_code})")

        if resp.status_code != 200:
            last_error = RuntimeError(
                f"LLM returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
            if attempt < 3:
                time.sleep(2)
            continue

        try:
            body = resp.json()
        except ValueError as exc:
            last_error = RuntimeError(f"Malformed JSON from LLM: {exc}")
            if attempt < 3:
                time.sleep(2)
            continue

        try:
            return body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected response structure from LLM: {body}"
            ) from exc

    raise RuntimeError(f"LLM call failed after 3 attempts: {last_error}") from last_error
