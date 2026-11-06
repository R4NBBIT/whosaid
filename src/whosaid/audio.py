"""오디오 파일 읽기 (mp3, m4a, wav, 동영상 등 대부분의 형식).

모든 처리는 16kHz 모노 float32로 통일합니다.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000

AUDIO_FILTER = (
    "오디오/동영상 (*.m4a *.mp3 *.wav *.aac *.flac *.ogg *.opus *.wma *.amr *.3gp *.webm *.mp4 *.mov *.mkv)"
)


def load(path: str | Path) -> np.ndarray:
    """오디오 파일을 16kHz 모노 float32 배열로 읽습니다."""
    import av

    chunks = []
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("이 파일에는 소리가 없습니다.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("소리를 읽지 못했습니다.")
    return (np.concatenate(chunks).astype(np.float32) / 32768.0).clip(-1.0, 1.0)


def duration(samples: np.ndarray) -> float:
    return len(samples) / SAMPLE_RATE


def cut(samples: np.ndarray, start: float, end: float) -> np.ndarray:
    a = max(0, int(start * SAMPLE_RATE))
    b = min(len(samples), int(end * SAMPLE_RATE))
    return samples[a:b]


def save_wav(samples: np.ndarray, path: str | Path) -> Path:
    path = Path(path)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return path


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
