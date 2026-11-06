"""실제 화자 분리/목소리 지문 모델로 하는 통합 테스트.

WHOSAID_TEST_MODELS 폴더에 아래 파일이 있을 때만 실행됩니다(CI에서는 내려받아 실행).
  sherpa-onnx-pyannote-segmentation-3-0/model.onnx
  3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx
  0-four-speakers-zh.wav   (sherpa-onnx 공개 예제 녹음, 레포에는 넣지 않음)
"""

import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from whosaid import audio, models
from whosaid.pipeline import Engine
from whosaid.settings import Settings

SRC = os.environ.get("WHOSAID_TEST_MODELS")
pytestmark = [
    pytest.mark.models,
    pytest.mark.skipif(not SRC, reason="WHOSAID_TEST_MODELS 가 없음"),
]


@pytest.fixture
def engine(isolated_home):
    src = Path(SRC)
    dst = isolated_home / "models"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / models.SEGMENTATION_DIR, dst / models.SEGMENTATION_DIR)
    shutil.copy(src / models.EMBEDDING_FILE, dst / models.EMBEDDING_FILE)
    return Engine(Settings())


@pytest.fixture
def samples():
    return audio.load(Path(SRC) / "0-four-speakers-zh.wav")


def test_enroll_from_one_clip_then_identify(engine, samples):
    a = engine.analyze("x.wav", samples=samples)
    assert len(a.speakers) == 4
    first = {}
    for t in a.turns:
        first.setdefault(t.cluster, t)
    names = {"S1": "가", "S2": "나", "S3": "다", "S4": "라"}
    d = engine.diarizer()
    for key, t in first.items():  # 각자 한 구간만으로 등록
        p = engine.store.add_person(names[key])
        engine.store.add_samples(p.id, d.embed(audio.cut(samples, t.start, t.end))[None],
                                 np.array([t.end - t.start]))
    correct = total = 0
    for t in a.turns:
        if first[t.cluster] is t or t.end - t.start < 1.0:
            continue
        best = engine.store.scores(d.embed(audio.cut(samples, t.start, t.end)))[0][0]
        correct += engine.store.get(best).name == names[t.cluster]
        total += 1
    assert total >= 5 and correct == total

    again = engine.analyze("x.wav", samples=samples)
    assert [s.name for s in again.speakers] == ["가", "나", "다", "라"]


def test_unenrolled_speaker_stays_unknown(engine, samples):
    a = engine.analyze("x.wav", samples=samples)
    engine.learn(a, {"S1": "가", "S2": "나", "S3": "다"})
    again = {s.key: s for s in engine.analyze("x.wav", samples=samples).speakers}
    assert again["S4"].person_id is None and again["S4"].name.startswith("참석자")
