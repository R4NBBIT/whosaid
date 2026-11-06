"""화자 분리(누가 언제 말했나)와 목소리 임베딩 추출 (sherpa-onnx, CPU)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from whosaid.audio import SAMPLE_RATE
from whosaid.progress import CancelToken, ProgressFn, no_progress
from whosaid.transcript import Turn
from whosaid.voiceprints import normalize

MIN_EMBED_SECONDS = 1.0  # 이보다 짧은 구간은 목소리 지문에 쓰지 않음
EMBED_WINDOW = 8.0  # 긴 구간은 이 길이로 잘라 여러 개의 지문을 만듦


@dataclass
class ClusterVoice:
    """한 녹음 안에서 한 화자의 목소리 정보."""

    key: str
    seconds: float
    embeddings: np.ndarray  # (N, D) 구간별 임베딩
    durations: np.ndarray  # (N,)
    centroid: np.ndarray | None
    sample_spans: list = field(default_factory=list)  # 들어볼 수 있는 대표 구간 [(start, end)]


class Diarizer:
    def __init__(self, segmentation_model: Path, embedding_model: Path, threads: int = 4) -> None:
        import sherpa_onnx as so

        self._so = so
        self.segmentation_model = str(segmentation_model)
        self.embedding_model = str(embedding_model)
        self.threads = threads
        self._extractor = so.SpeakerEmbeddingExtractor(
            so.SpeakerEmbeddingExtractorConfig(model=self.embedding_model, num_threads=threads)
        )

    def diarize(self, samples: np.ndarray, threshold: float = 0.5, num_speakers: int | None = None,
                progress: ProgressFn = no_progress, cancel: CancelToken | None = None) -> list[Turn]:
        so = self._so
        config = so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=self.segmentation_model),
                num_threads=self.threads,
            ),
            embedding=so.SpeakerEmbeddingExtractorConfig(model=self.embedding_model, num_threads=self.threads),
            clustering=so.FastClusteringConfig(
                num_clusters=num_speakers if num_speakers else -1, threshold=threshold
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        if not config.validate():
            raise RuntimeError("화자 분리 설정이 올바르지 않습니다.")
        sd = so.OfflineSpeakerDiarization(config)

        def callback(done: int, total: int) -> int:
            progress("diarize", done / total if total else None, "목소리 구분하는 중…")
            return 1 if (cancel and cancel.cancelled) else 0

        result = sd.process(samples, callback=callback).sort_by_start_time()
        if cancel:
            cancel.check()

        # 처음 등장한 순서대로 S1, S2, ... 로 이름 붙이기
        order: dict[int, str] = {}
        turns = []
        for seg in result:
            if seg.speaker not in order:
                order[seg.speaker] = f"S{len(order) + 1}"
            turns.append(Turn(float(seg.start), float(seg.end), order[seg.speaker]))
        return turns

    def embed(self, samples: np.ndarray) -> np.ndarray:
        stream = self._extractor.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        stream.input_finished()
        return normalize(np.array(self._extractor.compute(stream), dtype=np.float32))

    def cluster_voices(self, samples: np.ndarray, turns: list[Turn],
                       cancel: CancelToken | None = None) -> dict[str, ClusterVoice]:
        """화자별로 구간 임베딩을 모으고 평균 지문을 만듭니다."""
        by_key: dict[str, list[Turn]] = {}
        for t in turns:
            by_key.setdefault(t.cluster, []).append(t)

        voices = {}
        for key, ts in by_key.items():
            embs, durs = [], []
            for t in ts:
                if cancel:
                    cancel.check()
                s = t.start
                while t.end - s >= MIN_EMBED_SECONDS:
                    e = min(t.end, s + EMBED_WINDOW)
                    if t.end - e < MIN_EMBED_SECONDS:  # 짧게 남는 꼬리는 앞 조각에 붙임
                        e = t.end
                    a, b = int(s * SAMPLE_RATE), int(e * SAMPLE_RATE)
                    embs.append(self.embed(samples[a:b]))
                    durs.append(e - s)
                    s = e
            emb = np.stack(embs) if embs else np.zeros((0, 0), np.float32)
            dur = np.asarray(durs, np.float32)
            centroid = None
            if len(embs):
                w = np.sqrt(np.clip(dur, 0.5, 30.0))
                centroid = normalize((emb * w[:, None]).sum(axis=0))
            longest = sorted(ts, key=lambda t: t.start - t.end)[:3]
            voices[key] = ClusterVoice(
                key=key,
                seconds=float(sum(t.end - t.start for t in ts)),
                embeddings=emb,
                durations=dur,
                centroid=centroid,
                sample_spans=[(t.start, min(t.end, t.start + 12.0)) for t in longest],
            )
        return voices
