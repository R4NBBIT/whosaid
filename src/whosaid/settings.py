"""사용자 설정과 API 키 저장.

API 키는 settings.json과 분리된 secrets.json(사용자 폴더)에만 저장합니다.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from whosaid import paths


@dataclass
class Settings:
    # 음성 인식
    whisper_model: str = "large-v3-turbo"
    language: str = "ko"
    glossary: str = ""  # 참석자 이름, 자주 쓰는 용어 (인식 정확도 향상용)
    cpu_threads: int = 0  # 0이면 자동

    # 화자 분리 / 식별
    cluster_threshold: float = 0.5  # 낮을수록 화자를 더 잘게 나눔
    match_threshold: float = 0.5  # 등록된 목소리와 이 값 이상 비슷하면 그 사람으로 판단
    learn_from_meetings: bool = True  # 확인한 회의 결과로 목소리 지문을 보강

    # 요약
    summarizer: str = "local"  # none | local | anthropic | openai
    local_model: str = "qwen2.5-7b"
    local_accel: str = "cpu"  # cpu | vulkan(인텔 Arc 등 GPU, 실험적)
    local_context: int = 16384
    anthropic_model: str = "claude-sonnet-5-5"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""

    # 결과 저장 위치 (빈 값이면 문서\WhoSaid)
    output_dir: str = ""

    def resolved_output_dir(self):
        from pathlib import Path

        p = Path(self.output_dir) if self.output_dir else paths.default_output_dir()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def threads(self) -> int:
        if self.cpu_threads > 0:
            return self.cpu_threads
        return max(1, (os.cpu_count() or 4) - 1)

    @classmethod
    def load(cls) -> "Settings":
        p = paths.settings_path()
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        paths.settings_path().write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )


@dataclass
class Secrets:
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Secrets":
        s = cls()
        p = paths.secrets_path()
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                s = cls(**{k: v for k, v in raw.items() if k in {f.name for f in fields(cls)}})
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        # 환경변수가 있으면 우선
        s.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", s.anthropic_api_key)
        s.openai_api_key = os.environ.get("OPENAI_API_KEY", s.openai_api_key)
        return s

    def save(self) -> None:
        p = paths.secrets_path()
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
