"""프로그램 데이터 위치.

모든 개인 데이터(목소리 지문, 설정, API 키)와 모델은 레포 밖,
사용자 폴더에 저장됩니다. Windows에서는 %APPDATA%\\WhoSaid 입니다.
WHOSAID_HOME 환경변수로 위치를 바꿀 수 있습니다(테스트용).
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir, user_documents_dir

from whosaid import APP_NAME


def data_dir() -> Path:
    override = os.environ.get("WHOSAID_HOME")
    base = Path(override) if override else Path(user_data_dir(APP_NAME, appauthor=False, roaming=True))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    return _sub("models")


def voiceprints_dir() -> Path:
    return _sub("voiceprints")


def temp_dir() -> Path:
    return _sub("temp")


def settings_path() -> Path:
    return data_dir() / "settings.json"


def secrets_path() -> Path:
    return data_dir() / "secrets.json"


def default_output_dir() -> Path:
    override = os.environ.get("WHOSAID_HOME")
    if override:
        return Path(override) / "회의록"
    return Path(user_documents_dir()) / APP_NAME
