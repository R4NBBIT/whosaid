import httpx

from whosaid.settings import Secrets, Settings
from whosaid.summarize import create
from whosaid.summarize.base import Summarizer, split_chunks
from whosaid.summarize.openai_compat import OpenAICompatSummarizer
from whosaid.transcript import MeetingResult, Speaker, Utterance


def meeting(n=40):
    utts = [Utterance(i * 10, i * 10 + 8, "S1" if i % 2 else "S2", f"안건 {i}에 대해 이야기합니다." * 5) for i in range(n)]
    return MeetingResult("a.m4a", n * 10, "2026-11-06 10:00",
                         [Speaker("S1", 100, None, "민수"), Speaker("S2", 100, None, "지영")], utts)


class Fake(Summarizer):
    name = "fake"

    def __init__(self, max_chars):
        self.max_chars = max_chars
        self.calls = []

    def chat(self, system, user, max_tokens=2048):
        self.calls.append(user)
        return f"요약{len(self.calls)}"


def test_split_chunks_respects_limit():
    text = "\n".join("가" * 50 for _ in range(100))
    chunks = split_chunks(text, 500)
    assert len(chunks) > 1 and all(len(c) <= 520 for c in chunks)
    assert "\n".join(chunks) == text


def test_short_meeting_single_call():
    f = Fake(max_chars=1_000_000)
    assert f.summarize(meeting()) == "요약1"
    assert len(f.calls) == 1 and "민수" in f.calls[0]


def test_long_meeting_map_reduce():
    f = Fake(max_chars=2000)
    out = f.summarize(meeting())
    assert len(f.calls) > 2
    assert "부분별 메모" in f.calls[-1] and out == f"요약{len(f.calls)}"


def test_openai_compat_request(monkeypatch):
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, body=json, headers=headers)
        return httpx.Response(200, json={"choices": [{"message": {"content": "회의록"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    s = OpenAICompatSummarizer("http://localhost:11434/v1/", "qwen", api_key="")
    assert s.chat("sys", "user") == "회의록"
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in seen["headers"]


def test_factory_none_and_missing_key():
    s = Settings(summarizer="none")
    assert create(s) is None
    s.summarizer = "anthropic"
    try:
        create(s, Secrets())
    except ValueError as e:
        assert "API 키" in str(e)
    else:
        raise AssertionError("키가 없으면 오류여야 함")


def test_secrets_saved_outside_settings(isolated_home):
    sec = Secrets(anthropic_api_key="abc")
    sec.save()
    Settings().save()
    assert "abc" not in (isolated_home / "settings.json").read_text(encoding="utf-8")
    assert Secrets.load().anthropic_api_key == "abc"
