"""대본 데이터 구조와 화자 정렬, 내보내기."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from whosaid.audio import fmt_time


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Turn:
    """화자 분리 결과: start~end 동안 cluster 화자가 말함."""

    start: float
    end: float
    cluster: str


@dataclass
class Speaker:
    key: str  # 녹음 안에서의 화자 번호 (S1, S2, ...)
    seconds: float  # 말한 총 시간
    person_id: str | None = None  # 등록된 사람과 연결되면 그 id
    name: str = ""  # 화면에 보여줄 이름
    score: float = 0.0  # 연결된 사람과의 유사도
    candidates: list = field(default_factory=list)  # [(person_id, 이름, 유사도)]


@dataclass
class Utterance:
    start: float
    end: float
    speaker: str  # Speaker.key
    text: str


@dataclass
class MeetingResult:
    source: str
    duration: float
    created: str
    speakers: list[Speaker]
    utterances: list[Utterance]
    summary: str = ""
    summary_engine: str = ""

    def speaker_name(self, key: str) -> str:
        sp = next((s for s in self.speakers if s.key == key), None)
        return (sp.name if sp and sp.name else key) if sp else key

    # ------------------------------------------------------------ 내보내기
    def transcript_text(self, with_time: bool = True) -> str:
        lines = []
        for u in self.utterances:
            stamp = f"[{fmt_time(u.start)}] " if with_time else ""
            lines.append(f"{stamp}{self.speaker_name(u.speaker)}: {u.text}")
        return "\n".join(lines)

    def to_markdown(self, title: str = "") -> str:
        title = title or Path(self.source).stem
        names = [s.name or s.key for s in self.speakers if s.seconds > 0]
        out = [f"# {title}", "", f"- 일시: {self.created}", f"- 길이: {fmt_time(self.duration)}",
               f"- 참석자(발언 기준): {', '.join(names)}", ""]
        if self.summary:
            out += [self.summary.strip(), ""]
        out += ["## 전체 대본", ""]
        for u in self.utterances:
            out.append(f"**{self.speaker_name(u.speaker)}** `{fmt_time(u.start)}`  ")
            out.append(u.text)
            out.append("")
        return "\n".join(out)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "MeetingResult":
        raw = json.loads(text)
        raw["speakers"] = [Speaker(**s) for s in raw["speakers"]]
        raw["utterances"] = [Utterance(**u) for u in raw["utterances"]]
        return cls(**raw)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def assign_words(words: list[Word], turns: list[Turn], max_gap: float = 1.0) -> list[str | None]:
    """단어마다 가장 많이 겹치는 화자를 찾습니다. 겹치는 화자가 없으면 가까운 화자."""
    turns = sorted(turns, key=lambda t: t.start)
    result: list[str | None] = []
    j = 0
    for w in words:
        while j < len(turns) and turns[j].end < w.start - max_gap:
            j += 1
        best, best_ov, best_dist = None, 0.0, max_gap
        k = j
        while k < len(turns) and turns[k].start <= w.end + max_gap:
            t = turns[k]
            ov = _overlap(w.start, w.end, t.start, t.end)
            if ov > best_ov:
                best, best_ov = t.cluster, ov
            elif best_ov == 0.0:
                dist = min(abs(w.start - t.end), abs(t.start - w.end))
                if dist < best_dist:
                    best, best_dist = t.cluster, dist
            k += 1
        result.append(best)
    # 화자를 못 찾은 단어는 앞(없으면 뒤) 단어의 화자를 따름
    last = None
    for i, s in enumerate(result):
        if s is None:
            result[i] = last
        else:
            last = s
    nxt = None
    for i in range(len(result) - 1, -1, -1):
        if result[i] is None:
            result[i] = nxt
        else:
            nxt = result[i]
    return result


def build_utterances(words: list[Word], turns: list[Turn], pause_split: float = 30.0) -> list[Utterance]:
    """단어들을 같은 화자가 연달아 말한 발화 단위로 묶습니다."""
    if not words:
        return []
    speakers = assign_words(words, turns)
    utts: list[Utterance] = []
    for w, spk in zip(words, speakers):
        spk = spk or "S?"
        if utts and utts[-1].speaker == spk and w.start - utts[-1].end < pause_split:
            utts[-1].text += w.text
            utts[-1].end = w.end
        else:
            utts.append(Utterance(w.start, w.end, spk, w.text))
    for u in utts:
        u.text = " ".join(u.text.split())
    return [u for u in utts if u.text]
