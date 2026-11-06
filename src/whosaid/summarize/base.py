"""회의록 요약 공통 로직. 실제 모델 호출은 각 제공자가 chat()으로 구현합니다.

대본이 길면 나눠서 요약한 뒤 다시 합칩니다(로컬 모델은 한 번에 읽을 수 있는 양이 작음).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from whosaid.progress import CancelToken, ProgressFn, no_progress
from whosaid.transcript import MeetingResult

SYSTEM_PROMPT = """당신은 회의록을 작성하는 비서입니다. 주어진 회의 대본만 근거로 한국어 회의록을 작성합니다.
- 대본에 없는 내용은 지어내지 않습니다. 확실하지 않으면 "(확인 필요)"라고 적습니다.
- 발언자 이름은 대본에 적힌 그대로 씁니다.
- 음성 인식 오류로 보이는 단어는 문맥상 자연스럽게 고쳐 쓰되 뜻을 바꾸지 않습니다."""

FINAL_FORMAT = """다음 형식의 마크다운으로 작성하세요. 해당 내용이 없으면 "없음"이라고 쓰세요.

## 회의 요약
(3~5문장)

## 주요 논의
### (안건 제목)
- (누가 어떤 의견을 냈는지 중심으로)

## 결정 사항
-

## 할 일
| 담당자 | 할 일 | 기한 |
|---|---|---|

## 미결 / 다음 회의 안건
- """

CHUNK_PROMPT = """아래는 긴 회의 대본의 {idx}/{total} 부분입니다. 이 부분에서 나온 안건, 발언자별 주요 의견,
결정 사항, 할 일(담당자·기한), 미결 사항을 빠짐없이 간결한 글머리표로 정리하세요. 발언자 이름을 꼭 남기세요.

[대본]
{text}"""

MERGE_PROMPT = """아래는 한 회의를 여러 부분으로 나눠 정리한 메모입니다. 이것을 합쳐 하나의 회의록을 만드세요.
중복은 합치고, 시간 순서와 안건별로 정리하세요.

{fmt}

[부분별 메모]
{text}"""

SINGLE_PROMPT = """아래 회의 대본으로 회의록을 작성하세요.

{fmt}

[참석자]
{people}

[대본]
{text}"""


def split_chunks(text: str, max_chars: int) -> list[str]:
    lines, chunks, cur, size = text.splitlines(), [], [], 0
    for line in lines:
        if size + len(line) > max_chars and cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


class Summarizer(ABC):
    name = "summarizer"
    max_chars = 120_000  # 한 번에 보낼 대본 길이(글자)

    @abstractmethod
    def chat(self, system: str, user: str, max_tokens: int = 2048) -> str: ...

    def close(self) -> None:
        pass

    def summarize(self, result: MeetingResult, progress: ProgressFn = no_progress,
                  cancel: CancelToken | None = None) -> str:
        text = result.transcript_text(with_time=True)
        people = ", ".join(s.name or s.key for s in result.speakers if s.seconds > 0)
        if len(text) <= self.max_chars:
            progress("summarize", None, "회의록 정리하는 중…")
            return self.chat(SYSTEM_PROMPT, SINGLE_PROMPT.format(fmt=FINAL_FORMAT, people=people, text=text),
                             max_tokens=3000).strip()

        chunks = split_chunks(text, self.max_chars)
        notes = []
        for i, chunk in enumerate(chunks, 1):
            if cancel:
                cancel.check()
            progress("summarize", (i - 1) / (len(chunks) + 1), f"회의록 정리하는 중… ({i}/{len(chunks)} 부분)")
            notes.append(f"### 부분 {i}\n" + self.chat(
                SYSTEM_PROMPT, CHUNK_PROMPT.format(idx=i, total=len(chunks), text=chunk), max_tokens=1200))
        if cancel:
            cancel.check()
        progress("summarize", len(chunks) / (len(chunks) + 1), "회의록 합치는 중…")
        merged = "\n\n".join(notes)
        if len(merged) > self.max_chars:  # 메모도 너무 길면 한 번 더 줄임
            merged = merged[: self.max_chars]
        return self.chat(SYSTEM_PROMPT, MERGE_PROMPT.format(fmt=FINAL_FORMAT, text=merged), max_tokens=3000).strip()
