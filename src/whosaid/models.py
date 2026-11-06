"""AI 모델 내려받기와 위치 관리.

모델은 레포에 포함하지 않고, 처음 쓸 때 사용자 PC(%APPDATA%\\WhoSaid\\models)에 한 번 받아 둡니다.

- 화자 분리 / 목소리 지문: sherpa-onnx 배포본 (GitHub, 토큰 필요 없음)
- 음성 인식: faster-whisper (Hugging Face 공개 모델)
- 요약용 LLM: llama.cpp 실행 파일(GitHub) + GGUF 모델(Hugging Face 공개 모델)
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from whosaid import paths
from whosaid.progress import CancelToken, ProgressFn, no_progress

SHERPA_RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

SEGMENTATION_URL = f"{SHERPA_RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
SEGMENTATION_DIR = "sherpa-onnx-pyannote-segmentation-3-0"

# 4인 대화 녹음으로 비교했을 때 같은 사람/다른 사람 구분이 가장 확실하고 빨랐던 모델
EMBEDDING_ID = "3dspeaker_campplus_zh_en_advanced"
EMBEDDING_FILE = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
EMBEDDING_URL = f"{SHERPA_RELEASES}/speaker-recongition-models/{EMBEDDING_FILE}"

LLAMA_CPP_TAG = "b11000"


@dataclass(frozen=True)
class LocalLLM:
    key: str
    label: str
    repo: str
    filename: str
    size_gb: float


LOCAL_LLMS = {
    m.key: m
    for m in [
        LocalLLM(
            "qwen2.5-7b",
            "Qwen2.5 7B (추천, 약 4.7GB, RAM 16GB)",
            "bartowski/Qwen2.5-7B-Instruct-GGUF",
            "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            4.7,
        ),
        LocalLLM(
            "qwen2.5-3b",
            "Qwen2.5 3B (가벼움, 약 1.9GB, RAM 8GB)",
            "bartowski/Qwen2.5-3B-Instruct-GGUF",
            "Qwen2.5-3B-Instruct-Q4_K_M.gguf",
            1.9,
        ),
    ]
}

WHISPER_MODELS = {
    "large-v3-turbo": "정확도 높음 (추천, 약 1.6GB)",
    "medium": "중간 (약 1.5GB, 조금 빠름)",
    "small": "빠름 (약 0.5GB, 정확도 낮음)",
}


def download(url: str, dest: Path, progress: ProgressFn = no_progress, label: str = "",
             cancel: CancelToken | None = None) -> Path:
    """URL을 dest로 내려받습니다. 중간에 끊기면 다음 번에 이어서 받습니다(.part 파일)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with httpx.stream("GET", url, headers=headers, follow_redirects=True,
                      timeout=httpx.Timeout(30.0, read=120.0)) as r:
        if r.status_code == 416:  # 이미 다 받음
            tmp.replace(dest)
            return dest
        r.raise_for_status()
        if r.status_code != 206:
            have = 0  # 서버가 이어받기를 지원하지 않으면 처음부터
        total = int(r.headers.get("content-length") or 0)
        total = total + have if total else 0
        done = have
        with open(tmp, "ab" if have else "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                if cancel:
                    cancel.check()
                f.write(chunk)
                done += len(chunk)
                frac = done / total if total else None
                progress("download", frac, f"{label} 내려받는 중… {done / 1e6:.0f}MB"
                         + (f" / {total / 1e6:.0f}MB" if total else ""))
    tmp.replace(dest)
    return dest


def _extract(archive: Path, target: Path) -> None:
    target = target.resolve()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                if not (target / member).resolve().is_relative_to(target):
                    raise RuntimeError(f"압축 파일 경로가 이상합니다: {member}")
            zf.extractall(target)
    else:
        with tarfile.open(archive) as tf:
            tf.extractall(target, filter="data")


def segmentation_model(progress: ProgressFn = no_progress, cancel: CancelToken | None = None) -> Path:
    root = paths.models_dir()
    model = root / SEGMENTATION_DIR / "model.onnx"
    if not model.exists():
        archive = download(SEGMENTATION_URL, root / "segmentation.tar.bz2", progress, "화자 분리 모델", cancel)
        _extract(archive, root)
        archive.unlink()
    return model


def embedding_model(progress: ProgressFn = no_progress, cancel: CancelToken | None = None) -> Path:
    model = paths.models_dir() / EMBEDDING_FILE
    if not model.exists():
        download(EMBEDDING_URL, model, progress, "목소리 지문 모델", cancel)
    return model


def whisper_dir() -> Path:
    d = paths.models_dir() / "whisper"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _llama_asset(accel: str) -> tuple[str, str]:
    """(파일 이름, 실행 파일 이름)"""
    tag = LLAMA_CPP_TAG
    if sys.platform == "win32":
        kind = "vulkan" if accel == "vulkan" else "cpu"
        return f"llama-{tag}-bin-win-{kind}-x64.zip", "llama-server.exe"
    if sys.platform.startswith("linux"):
        kind = "ubuntu-vulkan-x64" if accel == "vulkan" else "ubuntu-x64"
        return f"llama-{tag}-bin-{kind}.tar.gz", "llama-server"
    if sys.platform == "darwin":
        return f"llama-{tag}-bin-macos-arm64.tar.gz", "llama-server"
    raise RuntimeError(f"지원하지 않는 운영체제입니다: {sys.platform}")


def llama_server(accel: str = "cpu", progress: ProgressFn = no_progress,
                 cancel: CancelToken | None = None) -> Path:
    asset, exe_name = _llama_asset(accel)
    target = paths.models_dir() / "llama.cpp" / f"{LLAMA_CPP_TAG}-{accel}"
    found = next(target.rglob(exe_name), None) if target.exists() else None
    if found:
        return found
    url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_TAG}/{asset}"
    archive = download(url, target.parent / asset, progress, "요약 엔진(llama.cpp)", cancel)
    try:
        if target.exists():
            shutil.rmtree(target)
        _extract(archive, target)
    finally:
        archive.unlink(missing_ok=True)
    found = next(target.rglob(exe_name), None)
    if not found:
        raise RuntimeError("요약 엔진 실행 파일을 찾지 못했습니다.")
    if sys.platform != "win32":
        found.chmod(0o755)
    return found


def local_llm(key: str, progress: ProgressFn = no_progress, cancel: CancelToken | None = None) -> Path:
    spec = LOCAL_LLMS.get(key)
    if spec is None and key.startswith("hf:") and key.count("/") >= 2:
        # 직접 지정: hf:사용자/저장소/파일이름.gguf
        repo, _, filename = key[3:].rpartition("/")
        spec = LocalLLM(key, key, repo, filename, 0)
    if spec is None:
        raise ValueError(f"알 수 없는 요약 모델: {key}")
    dest = paths.models_dir() / "llm" / spec.filename
    if dest.exists():
        return dest
    url = f"https://huggingface.co/{spec.repo}/resolve/main/{spec.filename}"
    return download(url, dest, progress, f"요약 모델({spec.key})", cancel)
