"""OpenAI 호환 API (OpenAI, Google Gemini, Ollama, 내장 llama.cpp 서버 등)."""

from __future__ import annotations

import httpx

from whosaid.summarize.base import Summarizer

PRESETS = {
    "OpenAI": "https://api.openai.com/v1",
    "Google Gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "Ollama (내 PC)": "http://localhost:11434/v1",
}


class OpenAICompatSummarizer(Summarizer):
    name = "openai"

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 600.0,
                 max_chars: int | None = None) -> None:
        if not model:
            raise ValueError("요약에 쓸 모델 이름을 설정에서 입력해 주세요.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        if max_chars:
            self.max_chars = max_chars

    def chat(self, system: str, user: str, max_tokens: int = 2048) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"요약 API 오류 ({r.status_code}): {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"] or ""
