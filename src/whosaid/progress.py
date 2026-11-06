"""작업 진행 상황 전달과 취소."""

from __future__ import annotations

import threading
from typing import Callable, Optional

# (단계 이름, 진행률 0~1 또는 모름=None, 화면에 보여줄 메시지)
ProgressFn = Callable[[str, Optional[float], str], None]


def no_progress(stage: str, fraction: Optional[float], message: str) -> None:
    pass


class Cancelled(Exception):
    """사용자가 작업을 취소함."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()
