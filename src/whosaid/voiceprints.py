"""목소리 지문 저장소.

사람마다 여러 개의 목소리 임베딩(192차원 벡터)을 모아 두고, 평균을 그 사람의 지문으로 씁니다.
녹음 원본은 저장하지 않고 벡터만 저장합니다. 위치: %APPDATA%\\WhoSaid\\voiceprints
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from whosaid import paths
from whosaid.models import EMBEDDING_ID

MAX_SAMPLES_PER_PERSON = 300


def normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


@dataclass
class Person:
    id: str
    name: str
    created: float
    updated: float
    samples: int = 0
    seconds: float = 0.0


class VoiceprintStore:
    def __init__(self, root: Path | None = None, embedding_id: str = EMBEDDING_ID) -> None:
        self.root = Path(root) if root else paths.voiceprints_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.embedding_id = embedding_id
        self._people: dict[str, Person] = {}
        self._cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self.stale_model: str | None = None  # 예전 모델로 만든 지문이 있으면 그 모델 이름
        self._load()

    # ---------------------------------------------------------------- 저장/읽기
    @property
    def _index_path(self) -> Path:
        return self.root / "index.json"

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        if raw.get("embedding_model") != self.embedding_id:
            # 다른 모델로 만든 지문은 비교할 수 없으므로 무시 (파일은 남겨 둠)
            self.stale_model = raw.get("embedding_model")
            return
        for p in raw.get("people", []):
            self._people[p["id"]] = Person(**p)

    def _save_index(self) -> None:
        data = {
            "embedding_model": self.embedding_id,
            "people": [asdict(p) for p in sorted(self._people.values(), key=lambda p: p.name)],
        }
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._index_path)

    def _npz(self, pid: str) -> Path:
        return self.root / f"{pid}.npz"

    def _arrays(self, pid: str) -> tuple[np.ndarray, np.ndarray]:
        if pid not in self._cache:
            f = self._npz(pid)
            if f.exists():
                with np.load(f) as z:
                    self._cache[pid] = (z["embeddings"].astype(np.float32), z["durations"].astype(np.float32))
            else:
                self._cache[pid] = (np.zeros((0, 0), np.float32), np.zeros((0,), np.float32))
        return self._cache[pid]

    # ---------------------------------------------------------------- 사람 관리
    def people(self) -> list[Person]:
        return sorted(self._people.values(), key=lambda p: p.name)

    def get(self, pid: str) -> Person | None:
        return self._people.get(pid)

    def find_by_name(self, name: str) -> Person | None:
        key = _name_key(name)
        return next((p for p in self._people.values() if _name_key(p.name) == key), None)

    def add_person(self, name: str) -> Person:
        name = name.strip()
        if not name:
            raise ValueError("이름이 비어 있습니다.")
        existing = self.find_by_name(name)
        if existing:
            return existing
        now = time.time()
        p = Person(id=uuid.uuid4().hex[:12], name=name, created=now, updated=now)
        self._people[p.id] = p
        self._save_index()
        return p

    def rename(self, pid: str, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("이름이 비어 있습니다.")
        other = self.find_by_name(name)
        if other and other.id != pid:
            raise ValueError(f"'{name}' 이름이 이미 있습니다.")
        self._people[pid].name = name
        self._save_index()

    def delete(self, pid: str) -> None:
        self._people.pop(pid, None)
        self._cache.pop(pid, None)
        self._npz(pid).unlink(missing_ok=True)
        self._save_index()

    def reset_samples(self, pid: str) -> None:
        self._cache.pop(pid, None)
        self._npz(pid).unlink(missing_ok=True)
        p = self._people[pid]
        p.samples, p.seconds, p.updated = 0, 0.0, time.time()
        self._save_index()

    # ---------------------------------------------------------------- 학습/비교
    def add_samples(self, pid: str, embeddings: np.ndarray, durations: np.ndarray) -> None:
        if pid not in self._people:
            raise KeyError(pid)
        new_e = np.stack([normalize(e) for e in np.atleast_2d(embeddings)]).astype(np.float32)
        new_d = np.asarray(durations, dtype=np.float32).reshape(-1)
        old_e, old_d = self._arrays(pid)
        if old_e.size:
            emb = np.concatenate([old_e, new_e])
            dur = np.concatenate([old_d, new_d])
        else:
            emb, dur = new_e, new_d
        if len(emb) > MAX_SAMPLES_PER_PERSON:  # 오래된 것부터 버림
            emb, dur = emb[-MAX_SAMPLES_PER_PERSON:], dur[-MAX_SAMPLES_PER_PERSON:]
        np.savez(self._npz(pid), embeddings=emb, durations=dur)
        self._cache[pid] = (emb, dur)
        p = self._people[pid]
        p.samples, p.seconds, p.updated = len(emb), float(dur.sum()), time.time()
        self._save_index()

    def centroid(self, pid: str) -> np.ndarray | None:
        emb, dur = self._arrays(pid)
        if not emb.size:
            return None
        w = np.sqrt(np.clip(dur, 0.5, 30.0))  # 긴 구간을 조금 더 믿되 한 구간이 독점하지 않게
        return normalize((emb * w[:, None]).sum(axis=0))

    def scores(self, vec: np.ndarray) -> list[tuple[str, float]]:
        """등록된 사람들과의 유사도(코사인). 높은 순."""
        v = normalize(vec)
        out = []
        for pid in self._people:
            c = self.centroid(pid)
            if c is not None and c.shape == v.shape:
                out.append((pid, float(c @ v)))
        return sorted(out, key=lambda x: -x[1])


def _name_key(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()
