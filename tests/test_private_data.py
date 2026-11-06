"""개인정보 검사기가 녹음·지문·키를 확실히 막는지 확인합니다.

실제 녹음 대신 파일 앞부분(매직 바이트)만 흉내 낸 가짜 데이터를 씁니다.
"""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_private_data", Path(__file__).resolve().parent.parent / "scripts" / "check_private_data.py"
)
cpd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpd)


@pytest.mark.parametrize("path", [
    "meeting.m4a", "a/b/rec.WAV", "voice.npz", "model.onnx", "x.gguf", "secrets.json", ".env.local",
    "voiceprints/index.json", "meetings/2026.md", "docs/recordings/a.txt",
])
def test_blocked_paths(path):
    assert cpd.check_path(path)


@pytest.mark.parametrize("path", ["src/whosaid/audio.py", "README.md", "packaging/whosaid.spec", "tests/test_x.py"])
def test_allowed_paths(path):
    assert not cpd.check_path(path)


@pytest.mark.parametrize("head", [
    b"RIFF\x00\x00\x00\x00WAVEfmt ",
    b"ID3\x04\x00",
    b"\x00\x00\x00\x20ftypM4A ",
    b"OggS\x00\x02",
    b"fLaC\x00",
    b"\x1aE\xdf\xa3",
    b"GGUF\x03\x00",
    b"\x93NUMPY\x01\x00",
])
def test_renamed_media_is_caught(head):
    assert cpd.check_content("innocent.txt", head + b"\x00" * 100)


def test_secrets_are_caught():
    fake_key = "sk-ant-" + "x" * 40  # 실제 키 모양을 실행 중에만 만듦
    assert cpd.check_content("config.py", f'KEY = "{fake_key}"'.encode())
    assert cpd.check_content("c.py", ("AIza" + "b" * 35).encode())


def test_normal_code_passes():
    assert not cpd.check_content("a.py", "print('안녕하세요')\n".encode())


def test_large_file_flagged():
    assert cpd.check_content("big.txt", b"a" * (cpd.MAX_BYTES + 1))
