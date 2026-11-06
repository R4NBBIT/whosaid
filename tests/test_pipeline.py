import numpy as np

from whosaid.diarize import ClusterVoice
from whosaid.pipeline import Analysis, Engine, apply_names, canonical_keys, is_placeholder_name, save_result
from whosaid.settings import Settings
from whosaid.transcript import Speaker, Turn, Word
from whosaid.voiceprints import VoiceprintStore, normalize


def make_analysis():
    rng = np.random.default_rng(1)
    voices = {}
    for k in ["S1", "S2", "S3"]:
        e = np.stack([normalize(rng.normal(0, 1, 192)) for _ in range(3)])
        voices[k] = ClusterVoice(k, 10.0, e, np.full(3, 3.0, np.float32), normalize(e.mean(0)), [(0.0, 3.0)])
    speakers = [Speaker("S1", 10, "p1", "민수", 0.9), Speaker("S2", 10, None, "참석자 1"),
                Speaker("S3", 10, "p1", "민수", 0.8)]
    turns = [Turn(0, 4, "S1"), Turn(4, 8, "S2"), Turn(8, 12, "S3")]
    return Analysis("회의.m4a", np.zeros(16000 * 12, np.float32), turns, voices, speakers)


def test_placeholder_names():
    assert is_placeholder_name("참석자 3") and is_placeholder_name("참석자12")
    assert not is_placeholder_name("참석자님") and not is_placeholder_name("민수")


def test_same_person_clusters_are_merged_in_result():
    a = make_analysis()
    assert canonical_keys(a.speakers) == {"S1": "S1", "S2": "S2", "S3": "S1"}
    eng = Engine(Settings(), VoiceprintStore())
    words = [Word(1, 2, " 하나"), Word(5, 6, " 둘"), Word(9, 10, " 셋")]
    r = eng.build_result(a, words)
    assert [s.key for s in r.speakers] == ["S1", "S2"]
    assert r.speakers[0].seconds == 20
    assert [(u.speaker, u.text) for u in r.utterances] == [("S1", "하나"), ("S2", "둘"), ("S1", "셋")]


def test_apply_names_updates_summary_and_learns(isolated_home):
    a = make_analysis()
    store = VoiceprintStore()
    eng = Engine(Settings(), store)
    r = eng.build_result(a, [Word(5, 6, " 둘")])
    r.summary = "참석자 1이 제안함. 참석자 10은 무관."
    learn = apply_names(r, a, {"S1": "민수", "S2": "지영"})
    assert r.summary == "지영이 제안함. 참석자 10은 무관."
    assert learn == {"S1": "민수", "S2": "지영", "S3": "민수"}
    learned = eng.learn(a, learn)
    assert sorted(set(learned)) == ["민수", "지영"]
    assert store.find_by_name("민수").samples == 6  # S1 + S3 합쳐서 학습


def test_placeholder_never_learned(isolated_home):
    a = make_analysis()
    store = VoiceprintStore()
    eng = Engine(Settings(), store)
    assert eng.learn(a, {"S2": "참석자 1"}) == []
    assert store.people() == []


def test_save_result_writes_markdown(isolated_home, tmp_path):
    a = make_analysis()
    r = Engine(Settings(), VoiceprintStore()).build_result(a, [Word(1, 2, " 안녕")])
    md = save_result(r, tmp_path, "주간/회의")
    assert md.exists() and "주간_회의" in md.name
    assert md.with_suffix(".whosaid.json").exists()
