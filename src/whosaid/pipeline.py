"""전체 흐름: 녹음 → 목소리 구분 → 등록된 사람 찾기 → 받아쓰기 → 회의록.

GUI와 CLI가 모두 이 모듈을 씁니다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from whosaid import audio, models
from whosaid.diarize import ClusterVoice, Diarizer
from whosaid.identify import identify
from whosaid.progress import CancelToken, ProgressFn, no_progress
from whosaid.settings import Secrets, Settings
from whosaid.transcript import MeetingResult, Speaker, Turn, Word, build_utterances
from whosaid.voiceprints import VoiceprintStore

# 단계별 전체 진행률 비중
STAGES = {"load": (0.0, 0.03), "diarize": (0.03, 0.18), "embed": (0.18, 0.22),
          "transcribe": (0.22, 0.85), "summarize": (0.85, 1.0)}


def staged(progress: ProgressFn, stage: str) -> ProgressFn:
    """단계 안의 진행률을 전체 진행률로 바꿔 전달합니다. 내려받기는 그대로 보여줍니다."""
    lo, hi = STAGES[stage]

    def inner(sub: str, frac, msg: str) -> None:
        if sub == "download":
            progress("download", frac, msg)
        else:
            progress(stage, None if frac is None else lo + (hi - lo) * frac, msg)

    return inner


@dataclass
class Analysis:
    """화자 분리 + 식별 결과 (받아쓰기 전 단계). 목소리 등록 화면에서도 씁니다."""

    source: str
    samples: np.ndarray
    turns: list[Turn]
    voices: dict[str, ClusterVoice]
    speakers: list[Speaker]


class Engine:
    def __init__(self, settings: Settings | None = None, store: VoiceprintStore | None = None) -> None:
        self.settings = settings or Settings.load()
        self.store = store or VoiceprintStore()
        self._diarizer: Diarizer | None = None
        self._transcriber = None
        self._transcriber_name = ""

    # ------------------------------------------------------------- 모델 준비
    def diarizer(self, progress: ProgressFn = no_progress, cancel: CancelToken | None = None) -> Diarizer:
        if self._diarizer is None:
            seg = models.segmentation_model(progress, cancel)
            emb = models.embedding_model(progress, cancel)
            self._diarizer = Diarizer(seg, emb, self.settings.threads())
        return self._diarizer

    def transcriber(self, progress: ProgressFn = no_progress):
        name = self.settings.whisper_model
        if self._transcriber is None or self._transcriber_name != name:
            from whosaid.transcribe import Transcriber

            self._transcriber = Transcriber(name, self.settings.threads(), progress)
            self._transcriber_name = name
        return self._transcriber

    # ------------------------------------------------------------- 단계
    def analyze(self, path: str | Path, num_speakers: int | None = None, progress: ProgressFn = no_progress,
                cancel: CancelToken | None = None, samples: np.ndarray | None = None) -> Analysis:
        p = staged(progress, "load")
        p("load", 0.0, "녹음 파일 읽는 중…")
        if samples is None:
            samples = audio.load(path)
        if audio.duration(samples) < 2.0:
            raise ValueError("녹음이 너무 짧습니다.")
        d = self.diarizer(p, cancel)

        turns = d.diarize(samples, self.settings.cluster_threshold, num_speakers,
                          staged(progress, "diarize"), cancel)
        if not turns:
            raise ValueError("말소리를 찾지 못했습니다.")
        p = staged(progress, "embed")
        p("embed", 0.0, "목소리 지문 비교하는 중…")
        voices = d.cluster_voices(samples, turns, cancel)
        speakers = identify(voices, self.store, self.settings.match_threshold)
        p("embed", 1.0, "목소리 지문 비교 완료")
        return Analysis(str(path), samples, turns, voices, speakers)

    def transcribe(self, analysis: Analysis, progress: ProgressFn = no_progress,
                   cancel: CancelToken | None = None) -> list[Word]:
        from whosaid.transcribe import speech_regions

        t = self.transcriber(staged(progress, "load"))
        regions = speech_regions(analysis.turns, audio.duration(analysis.samples))
        return t.transcribe(analysis.samples, self.settings.language, self.settings.glossary,
                            staged(progress, "transcribe"), cancel, regions)

    def build_result(self, analysis: Analysis, words: list[Word]) -> MeetingResult:
        # 같은 사람으로 판정된 화자들은 대본에서 하나로 합침
        canonical = canonical_keys(analysis.speakers)
        turns = [Turn(t.start, t.end, canonical.get(t.cluster, t.cluster)) for t in analysis.turns]
        speakers = []
        for sp in analysis.speakers:
            if canonical[sp.key] == sp.key:
                merged = sum(s.seconds for s in analysis.speakers if canonical[s.key] == sp.key)
                speakers.append(Speaker(sp.key, round(merged, 1), sp.person_id, sp.name, sp.score, sp.candidates))
        return MeetingResult(
            source=Path(analysis.source).name,
            duration=round(audio.duration(analysis.samples), 1),
            created=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            speakers=speakers,
            utterances=build_utterances(words, turns),
        )

    def summarize(self, result: MeetingResult, progress: ProgressFn = no_progress,
                  cancel: CancelToken | None = None, secrets: Secrets | None = None) -> None:
        from whosaid import summarize

        p = staged(progress, "summarize")
        s = summarize.create(self.settings, secrets, p, cancel)
        if s is None:
            return
        try:
            result.summary = s.summarize(result, p, cancel)
            result.summary_engine = s.name
        finally:
            s.close()

    def process(self, path: str | Path, num_speakers: int | None = None, do_summary: bool = True,
                progress: ProgressFn = no_progress, cancel: CancelToken | None = None
                ) -> tuple[Analysis, MeetingResult]:
        analysis = self.analyze(path, num_speakers, progress, cancel)
        words = self.transcribe(analysis, progress, cancel)
        result = self.build_result(analysis, words)
        if do_summary:
            try:
                self.summarize(result, progress, cancel)
            except Exception as e:  # 요약이 실패해도 대본은 살림
                from whosaid.progress import Cancelled

                if isinstance(e, Cancelled):
                    raise
                result.summary = f"> 요약을 만들지 못했습니다: {e}"
        progress("done", 1.0, "완료")
        return analysis, result

    # ------------------------------------------------------------- 학습
    def learn(self, analysis: Analysis, names: dict[str, str]) -> list[str]:
        """화자 번호 → 이름 대응을 받아 목소리 지문에 추가합니다. 이름이 빈 화자는 건너뜁니다.

        반환: 학습한 사람 이름 목록
        """
        learned = []
        for key, name in names.items():
            name = (name or "").strip()
            if is_placeholder_name(name):
                continue
            voice = analysis.voices.get(key)
            if not name or voice is None or not len(voice.embeddings):
                continue
            person = self.store.add_person(name)
            self.store.add_samples(person.id, voice.embeddings, voice.durations)
            learned.append(person.name)
        return learned


def canonical_keys(speakers: list[Speaker]) -> dict[str, str]:
    """같은 사람으로 판정된 화자 번호들을 첫 번째 번호로 모읍니다. {화자번호: 대표 화자번호}"""
    canonical: dict[str, str] = {}
    first_of_person: dict[str, str] = {}
    for sp in speakers:
        canonical[sp.key] = first_of_person.setdefault(sp.person_id, sp.key) if sp.person_id else sp.key
    return canonical


def apply_names(result: MeetingResult, analysis: Analysis, names: dict[str, str]) -> dict[str, str]:
    """확인한 이름을 결과에 반영합니다(요약 속 이름도 바꿈). 학습용 {원래 화자번호: 이름}을 돌려줍니다."""
    for sp in result.speakers:
        new = (names.get(sp.key) or "").strip()
        if new and new != sp.name:
            if result.summary and sp.name:
                result.summary = re.sub(re.escape(sp.name) + r"(?!\d)", new, result.summary)
            sp.name = new
    canonical = canonical_keys(analysis.speakers)
    learn = {}
    for k, c in canonical.items():
        name = (names.get(c) or "").strip()
        learn[k] = "" if is_placeholder_name(name) else name
    return learn


def is_placeholder_name(name: str) -> bool:
    """'참석자 3'처럼 자동으로 붙인 이름인지."""
    return bool(re.fullmatch(r"참석자\s*\d+", name.strip()))


def save_result(result: MeetingResult, out_dir: Path, title: str = "") -> Path:
    """회의록(.md)과 다시 열기용 데이터(.whosaid.json)를 저장합니다."""
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    base = re.sub(r'[\\/:*?"<>|]+', "_", title or Path(result.source).stem).strip() or "회의"
    md = out_dir / f"{stamp}_{base}.md"
    md.write_text(result.to_markdown(title), encoding="utf-8")
    md.with_suffix(".whosaid.json").write_text(result.to_json(), encoding="utf-8")
    return md
