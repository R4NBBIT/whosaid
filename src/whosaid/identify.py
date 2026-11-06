"""녹음 속 화자를 등록된 사람과 연결합니다.

1) 유사도가 높은 짝부터 1:1로 연결합니다(한 사람이 두 화자를 동시에 가져가지 않게).
2) 화자 분리가 한 사람을 둘로 나눈 경우를 위해, 남은 화자가 이미 연결된 사람과
   아주 비슷하면(기준 + 여유값 이상, 그리고 먼저 연결된 화자와 비슷한 수준) 같은 사람으로 합칩니다.
3) 그 외에는 '참석자 N'으로 남깁니다.
"""

from __future__ import annotations

import numpy as np

from whosaid.diarize import ClusterVoice
from whosaid.transcript import Speaker
from whosaid.voiceprints import VoiceprintStore

MERGE_MARGIN = 0.12
MERGE_GAP = 0.15


def identify(voices: dict[str, ClusterVoice], store: VoiceprintStore, threshold: float) -> list[Speaker]:
    keys = sorted(voices, key=lambda k: int(k[1:]) if k[1:].isdigit() else 0)
    score_table: dict[str, list[tuple[str, float]]] = {}
    for k in keys:
        c = voices[k].centroid
        score_table[k] = store.scores(c) if c is not None else []

    pairs = sorted(
        ((s, k, pid) for k in keys for pid, s in score_table[k] if s >= threshold),
        reverse=True,
    )
    assigned: dict[str, tuple[str, float]] = {}
    taken: set[str] = set()
    for s, k, pid in pairs:
        if k in assigned or pid in taken:
            continue
        assigned[k] = (pid, s)
        taken.add(pid)
    best_of = {pid: s for _, (pid, s) in assigned.items()}
    for k in keys:
        if k in assigned or not score_table[k]:
            continue
        pid, s = score_table[k][0]
        # 이미 그 사람으로 연결된 화자만큼 비슷해야 같은 사람이 둘로 나뉜 것으로 봄
        if pid in taken and s >= threshold + MERGE_MARGIN and s >= best_of[pid] - MERGE_GAP:
            assigned[k] = (pid, s)

    speakers = []
    unknown_n = 0
    for k in keys:
        cands = [(pid, store.get(pid).name, round(s, 3)) for pid, s in score_table[k][:3]]
        sp = Speaker(key=k, seconds=round(voices[k].seconds, 1), candidates=cands)
        if k in assigned:
            pid, s = assigned[k]
            sp.person_id, sp.name, sp.score = pid, store.get(pid).name, round(s, 3)
        else:
            unknown_n += 1
            sp.name = f"참석자 {unknown_n}"
            sp.score = round(score_table[k][0][1], 3) if score_table[k] else 0.0
        speakers.append(sp)
    return speakers


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
