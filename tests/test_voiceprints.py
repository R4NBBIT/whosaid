import json

import numpy as np
import pytest

from whosaid.diarize import ClusterVoice
from whosaid.identify import identify
from whosaid.voiceprints import VoiceprintStore, normalize

rng = np.random.default_rng(0)
DIM = 192


def voice_of(base, n=5, noise=0.3):
    return np.stack([normalize(base + rng.normal(0, noise, DIM)) for _ in range(n)])


def cluster(key, emb):
    return ClusterVoice(key, 30.0, emb, np.full(len(emb), 6.0, np.float32), normalize(emb.mean(0)))


@pytest.fixture
def people():
    return {name: rng.normal(0, 1, DIM) for name in ["민수", "지영", "하늘"]}


@pytest.fixture
def store(people):
    s = VoiceprintStore()
    for name, base in people.items():
        p = s.add_person(name)
        s.add_samples(p.id, voice_of(base), np.full(5, 5.0))
    return s


def test_persist_and_reload(store):
    again = VoiceprintStore(store.root)
    assert [p.name for p in again.people()] == sorted(["민수", "지영", "하늘"])
    p = again.find_by_name("민 수")  # 띄어쓰기 무시
    assert p and p.samples == 5 and again.centroid(p.id).shape == (DIM,)


def test_rename_delete_reset(store):
    p = store.find_by_name("하늘")
    with pytest.raises(ValueError):
        store.rename(p.id, "민수")
    store.rename(p.id, "하늘이")
    assert store.find_by_name("하늘이")
    store.reset_samples(p.id)
    assert store.centroid(p.id) is None
    store.delete(p.id)
    assert not store.find_by_name("하늘이")


def test_other_model_voiceprints_are_ignored(store):
    idx = store.root / "index.json"
    data = json.loads(idx.read_text(encoding="utf-8"))
    data["embedding_model"] = "old-model"
    idx.write_text(json.dumps(data), encoding="utf-8")
    again = VoiceprintStore(store.root)
    assert again.people() == [] and again.stale_model == "old-model"


def test_identify_known_and_unknown(store, people):
    stranger = rng.normal(0, 1, DIM)
    voices = {
        "S1": cluster("S1", voice_of(people["지영"])),
        "S2": cluster("S2", voice_of(people["민수"])),
        "S3": cluster("S3", voice_of(stranger)),
    }
    spk = {s.key: s for s in identify(voices, store, threshold=0.5)}
    assert spk["S1"].name == "지영"
    assert spk["S2"].name == "민수"
    assert spk["S3"].person_id is None and spk["S3"].name == "참석자 1"


def test_one_person_split_in_two_is_merged(store, people):
    voices = {"S1": cluster("S1", voice_of(people["민수"])), "S2": cluster("S2", voice_of(people["민수"]))}
    spk = identify(voices, store, threshold=0.5)
    assert [s.name for s in spk] == ["민수", "민수"]


def test_not_merged_when_only_vaguely_similar(store, people):
    # 민수와 어느 정도 닮았지만 다른 사람
    lookalike = people["민수"] * 0.6 + rng.normal(0, 1, DIM) * 0.8
    voices = {"S1": cluster("S1", voice_of(people["민수"])), "S2": cluster("S2", voice_of(lookalike))}
    spk = {s.key: s for s in identify(voices, store, threshold=0.5)}
    assert spk["S1"].name == "민수"
    assert spk["S2"].person_id is None
