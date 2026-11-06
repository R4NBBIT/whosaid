"""요약 제공자 선택."""

from __future__ import annotations

from whosaid.progress import CancelToken, ProgressFn, no_progress
from whosaid.settings import Secrets, Settings
from whosaid.summarize.base import Summarizer

LABELS = {
    "none": "요약 안 함 (대본만)",
    "local": "PC 안에서 처리 (내장 모델)",
    "anthropic": "Claude API",
    "openai": "OpenAI 호환 API (OpenAI, Gemini, Ollama 등)",
}


def create(settings: Settings, secrets: Secrets | None = None, progress: ProgressFn = no_progress,
           cancel: CancelToken | None = None) -> Summarizer | None:
    kind = settings.summarizer
    if kind == "none":
        return None
    secrets = secrets or Secrets.load()
    if kind == "local":
        from whosaid.summarize.local_llama import LocalLlamaSummarizer

        return LocalLlamaSummarizer(settings.local_model, settings.local_accel, settings.local_context,
                                    settings.threads(), progress, cancel)
    if kind == "anthropic":
        from whosaid.summarize.anthropic_api import AnthropicSummarizer

        return AnthropicSummarizer(secrets.anthropic_api_key, settings.anthropic_model)
    if kind == "openai":
        from whosaid.summarize.openai_compat import OpenAICompatSummarizer

        return OpenAICompatSummarizer(settings.openai_base_url, settings.openai_model, secrets.openai_api_key)
    raise ValueError(f"알 수 없는 요약 방식: {kind}")
