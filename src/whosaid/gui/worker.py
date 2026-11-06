"""오래 걸리는 작업을 화면이 멈추지 않게 별도 스레드에서 실행."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from whosaid.progress import CancelToken, Cancelled


class Task(QThread):
    progressed = Signal(str, float, str)  # 단계, 진행률(-1=모름), 메시지
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], parent=None) -> None:
        """fn(progress, cancel) 형태의 함수를 실행합니다."""
        super().__init__(parent)
        self.fn = fn
        self.token = CancelToken()

    def cancel(self) -> None:
        self.token.cancel()

    def _progress(self, stage: str, frac, msg: str) -> None:
        self.progressed.emit(stage, -1.0 if frac is None else float(frac), msg)

    def run(self) -> None:
        try:
            result = self.fn(self._progress, self.token)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # 화면에 오류를 보여주기 위해 모두 잡음
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.succeeded.emit(result)
