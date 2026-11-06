"""Anthropic Claude API."""

from __future__ import annotations

import httpx

from whosaid.summarize.base import Summarizer


class AnthropicSummarizer(Summarizer):
    name = "anthropic"
    max_chars = 300_000

    def __init__(self, api_key: str, model: str, timeout: float = 600.0) -> None:
        if not api_key:
            raise ValueError("설정에서 Anthropic API 키를 입력해 주세요.")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, system: str, user: str, max_tokens: int = 2048) -> str:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Claude API 오류 ({r.status_code}): {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
