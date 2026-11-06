"""음성 인식 (faster-whisper, CPU int8).

faster-whisper의 VAD(무음 건너뛰기)는 onnxruntime 패키지를 불러오는데, 화자 분리용 sherpa-onnx가
윈도우에서 자기 onnxruntime.dll을 따로 들고 있어 두 버전이 충돌할 수 있습니다.
그래서 VAD 대신 화자 분리에서 찾은 말소리 구간(clip_timestamps)만 받아씁니다.
"""

from __future__ import annotations

import numpy as np

from whosaid import models
from whosaid.audio import SAMPLE_RATE
from whosaid.progress import CancelToken, ProgressFn, no_progress
from whosaid.transcript import Word


class Transcriber:
    def __init__(self, model_name: str = "large-v3-turbo", threads: int = 4,
                 progress: ProgressFn = no_progress) -> None:
        from faster_whisper import WhisperModel

        progress("load", None, "음성 인식 모델 준비 중… (처음 한 번은 내려받느라 몇 분 걸려요)")
        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=threads,
            download_root=str(models.whisper_dir()),
        )

    def transcribe(self, samples: np.ndarray, language: str = "ko", glossary: str = "",
                   progress: ProgressFn = no_progress, cancel: CancelToken | None = None,
                   regions: list[tuple[float, float]] | None = None) -> list[Word]:
        """regions: 받아쓸 말소리 구간 [(시작초, 끝초)]. 없으면 전체."""
        total = len(samples) / SAMPLE_RATE
        prompt = None
        if glossary.strip():
            terms = ", ".join(t.strip() for t in glossary.replace("\n", ",").split(",") if t.strip())
            prompt = f"회의 참석자와 용어: {terms}."
        segments, _info = self.model.transcribe(
            samples,
            language=language or None,
            beam_size=5,
            word_timestamps=True,
            vad_filter=False,
            clip_timestamps=[t for r in regions for t in r] if regions else "0",
            condition_on_previous_text=False,  # 같은 말 반복(환각) 줄이기
            initial_prompt=prompt,
        )
        words: list[Word] = []
        for seg in segments:
            if cancel:
                cancel.check()
            if seg.words:
                words.extend(Word(float(w.start), float(w.end), w.word) for w in seg.words)
            elif seg.text.strip():
                words.append(Word(float(seg.start), float(seg.end), " " + seg.text.strip()))
            progress("transcribe", min(1.0, seg.end / total) if total else None,
                     f"받아쓰는 중… {int(seg.end // 60)}분 / {int(total // 60)}분")
        return words


def speech_regions(turns, total: float, pad: float = 0.4, join_gap: float = 1.5,
                   max_len: float = 600.0) -> list[tuple[float, float]]:
    """화자 분리 구간들을 앞뒤로 조금 늘리고, 가까운 것끼리 합쳐 받아쓸 구간을 만듭니다."""
    spans = sorted((max(0.0, t.start - pad), min(total, t.end + pad)) for t in turns)
    out: list[list[float]] = []
    for s, e in spans:
        if out and s - out[-1][1] <= join_gap and e - out[-1][0] <= max_len:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(round(s, 2), round(e, 2)) for s, e in out]
