#!/usr/bin/env python3
"""회의 녹음·목소리 지문·회의록·모델·API 키가 레포에 들어가는 것을 막는 검사기.

사용법:
    python scripts/check_private_data.py --staged   # 커밋 직전 (pre-commit 훅이 실행)
    python scripts/check_private_data.py --all      # 레포에 추적 중인 모든 파일 (CI가 실행)
    python scripts/check_private_data.py FILE ...   # 지정한 파일만

파일 확장자만 보지 않고, 파일 앞부분(매직 바이트)과 내용까지 확인하므로
확장자를 바꾼 오디오 파일이나 코드에 붙여 넣은 API 키도 잡아냅니다.
문제가 하나라도 있으면 종료 코드 1을 돌려줍니다.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import zipfile
from pathlib import PurePosixPath

MAX_BYTES = 2 * 1024 * 1024  # 2MB 넘는 파일은 일단 의심

BLOCKED_EXTENSIONS = {
    # 오디오 / 비디오
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma",
    ".amr", ".3gp", ".3ga", ".webm", ".mp4", ".m4v", ".mov", ".mkv", ".avi",
    ".caf", ".aiff", ".aif",
    # 목소리 지문 / 배열 데이터
    ".npy", ".npz", ".pkl", ".pickle",
    # 모델
    ".onnx", ".gguf", ".bin", ".safetensors", ".pt", ".pth", ".ckpt",
    # 비밀값
    ".key", ".pem",
}

BLOCKED_DIR_NAMES = {
    "voiceprints", "meetings", "minutes", "recordings", "whosaid-data",
}

BLOCKED_FILE_NAMES = {"secrets.json", ".env"}

# (설명, 앞부분 바이트를 받아 True/False)
MAGIC_CHECKS = [
    ("WAV 오디오", lambda b: b[:4] == b"RIFF" and b[8:12] in (b"WAVE", b"AVI ")),
    ("MP3 오디오", lambda b: b[:3] == b"ID3" or (len(b) > 1 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0)),
    ("FLAC 오디오", lambda b: b[:4] == b"fLaC"),
    ("OGG/OPUS 오디오", lambda b: b[:4] == b"OggS"),
    ("MP4/M4A 미디어", lambda b: b[4:8] == b"ftyp"),
    ("WebM/MKV 미디어", lambda b: b[:4] == b"\x1aE\xdf\xa3"),
    ("AMR 오디오", lambda b: b[:5] == b"#!AMR"),
    ("CAF 오디오", lambda b: b[:4] == b"caff"),
    ("AIFF 오디오", lambda b: b[:4] == b"FORM" and b[8:12] in (b"AIFF", b"AIFC")),
    ("GGUF 모델", lambda b: b[:4] == b"GGUF"),
    ("NumPy 배열(목소리 지문일 수 있음)", lambda b: b[:6] == b"\x93NUMPY"),
    ("pickle 데이터", lambda b: b[:2] in (b"\x80\x04", b"\x80\x05")),
]

SECRET_PATTERNS = [
    ("Anthropic API 키", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API 키", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("Google API 키", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Hugging Face 토큰", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("GitHub 토큰", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def staged_files() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [p for p in out.decode("utf-8").split("\0") if p]


def tracked_files() -> list[str]:
    out = _git("ls-files", "-z")
    return [p for p in out.decode("utf-8").split("\0") if p]


def read_staged(path: str) -> bytes:
    return _git("show", f":{path}")


def read_worktree(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def check_path(path: str) -> list[str]:
    problems = []
    p = PurePosixPath(path.replace("\\", "/"))
    if p.suffix.lower() in BLOCKED_EXTENSIONS:
        problems.append(f"금지된 파일 형식({p.suffix})")
    if p.name in BLOCKED_FILE_NAMES or p.name.startswith(".env."):
        problems.append("비밀값 파일")
    for part in p.parts[:-1]:
        if part.lower() in BLOCKED_DIR_NAMES or part.lower().startswith("voiceprint"):
            problems.append(f"개인 데이터 폴더({part}/)")
            break
    return problems


def check_content(path: str, data: bytes) -> list[str]:
    problems = []
    if len(data) > MAX_BYTES:
        problems.append(f"파일이 너무 큼({len(data) / 1024 / 1024:.1f}MB) - 녹음이나 모델일 수 있음")
    head = data[:64]
    for label, test in MAGIC_CHECKS:
        try:
            if test(head):
                problems.append(f"내용이 {label}로 보임")
                break
        except IndexError:
            pass
    if head[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
            if any(n.lower().endswith((".npy", ".wav", ".mp3", ".m4a")) for n in names):
                problems.append("압축 파일 안에 오디오/목소리 지문이 있음")
        except zipfile.BadZipFile:
            pass
    text = data.decode("utf-8", errors="ignore")
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            problems.append(f"{label}로 보이는 문자열")
    return problems


def run(paths: list[str], reader) -> int:
    failures = []
    for path in paths:
        problems = check_path(path)
        try:
            problems += check_content(path, reader(path))
        except (OSError, subprocess.CalledProcessError):
            pass
        if problems:
            failures.append((path, problems))

    if not failures:
        return 0

    print("\n[WhoSaid 개인정보 검사] 커밋하면 안 되는 파일이 있습니다:\n", file=sys.stderr)
    for path, problems in failures:
        print(f"  - {path}: {', '.join(dict.fromkeys(problems))}", file=sys.stderr)
    print(
        "\n이 레포는 공개(Public)입니다. 회의 녹음, 목소리 지문, 회의록, 모델, API 키는 올리지 마세요.\n"
        "실수로 추가했다면: git restore --staged <파일>\n",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="커밋 대기 중인 파일 검사")
    group.add_argument("--all", action="store_true", help="추적 중인 모든 파일 검사")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    if args.staged:
        return run(staged_files(), read_staged)
    if args.all:
        return run(tracked_files(), read_worktree)
    if args.files:
        return run(args.files, read_worktree)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
