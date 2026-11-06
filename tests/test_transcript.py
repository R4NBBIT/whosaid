from whosaid.transcript import MeetingResult, Speaker, Turn, Word, assign_words, build_utterances

TURNS = [Turn(0.0, 5.0, "S1"), Turn(5.2, 9.0, "S2"), Turn(12.0, 15.0, "S1")]


def test_assign_by_overlap_and_nearest():
    words = [Word(1, 1.5, " 안녕"), Word(4.8, 5.6, " 네"), Word(6, 6.5, " 좋아요"), Word(10.5, 10.8, " 음"),
             Word(13, 13.4, " 그럼")]
    spk = assign_words(words, TURNS)
    assert spk[0] == "S1"
    assert spk[1] == "S2"  # 5.2~5.6이 더 많이 겹침
    assert spk[2] == "S2"
    assert spk[3] == "S2"  # 어느 화자와도 안 겹침 → 앞 단어의 화자를 따름
    assert spk[4] == "S1"


def test_build_utterances_groups_consecutive_words():
    words = [Word(1, 1.5, " 오늘"), Word(1.6, 2.0, " 회의"), Word(6, 6.5, " 네"), Word(13, 13.4, " 시작")]
    utts = build_utterances(words, TURNS)
    assert [(u.speaker, u.text) for u in utts] == [("S1", "오늘 회의"), ("S2", "네"), ("S1", "시작")]


def test_markdown_and_json_roundtrip():
    r = MeetingResult(
        source="w.m4a", duration=15, created="2026-11-06 10:00",
        speakers=[Speaker("S1", 8, "p1", "민수", 0.9), Speaker("S2", 4, None, "참석자 1")],
        utterances=build_utterances([Word(1, 2, " 안녕"), Word(6, 7, " 네")], TURNS),
        summary="## 회의 요약\n좋았음",
    )
    md = r.to_markdown("주간회의")
    assert "# 주간회의" in md and "**민수**" in md and "**참석자 1**" in md and "## 회의 요약" in md
    assert "민수: 안녕" in r.transcript_text()
    back = MeetingResult.from_json(r.to_json())
    assert back.speakers[0].name == "민수" and back.utterances[1].text == "네"


def test_speech_regions_merge_and_pad():
    from whosaid.transcribe import speech_regions

    turns = [Turn(1.0, 3.0, "S1"), Turn(3.5, 5.0, "S2"), Turn(20.0, 22.0, "S1")]
    assert speech_regions(turns, total=21.5) == [(0.6, 5.4), (19.6, 21.5)]
