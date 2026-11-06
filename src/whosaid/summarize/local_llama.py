"""내장 요약: llama.cpp 서버를 PC에서 잠깐 띄워 GGUF 모델로 요약합니다. 인터넷으로 아무것도 보내지 않습니다."""

from __future__ import annotations

import atexit
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from whosaid import models, paths
from whosaid.progress import CancelToken, ProgressFn, no_progress
from whosaid.summarize.openai_compat import OpenAICompatSummarizer


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalLlamaSummarizer(OpenAICompatSummarizer):
    name = "local"

    def __init__(self, model_key: str, accel: str = "cpu", context: int = 16384, threads: int = 4,
                 progress: ProgressFn = no_progress, cancel: CancelToken | None = None) -> None:
        server = models.llama_server(accel, progress, cancel)
        gguf = models.local_llm(model_key, progress, cancel)
        port = _free_port()
        super().__init__(f"http://127.0.0.1:{port}/v1", model=model_key, timeout=3600.0,
                         max_chars=int(context * 0.65))
        self.proc = self._start(server, gguf, port, accel, context, threads, progress, cancel)

    def _start(self, server: Path, gguf: Path, port: int, accel: str, context: int, threads: int,
               progress: ProgressFn, cancel: CancelToken | None) -> subprocess.Popen:
        args = [str(server), "-m", str(gguf), "--host", "127.0.0.1", "--port", str(port),
                "-c", str(context), "-t", str(threads), "--no-webui"]
        args += ["-ngl", "99"] if accel == "vulkan" else ["-ngl", "0"]
        log = open(paths.temp_dir() / "llama-server.log", "wb")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd=str(server.parent),
                                creationflags=flags)
        atexit.register(_kill, proc)
        progress("load", None, "요약 모델 불러오는 중…")
        deadline = time.time() + 600
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("요약 엔진이 시작되지 않았습니다. 로그: "
                                   + str(paths.temp_dir() / "llama-server.log"))
            if cancel and cancel.cancelled:
                _kill(proc)
                cancel.check()
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                    return proc
            except httpx.HTTPError:
                pass
            time.sleep(1)
        _kill(proc)
        raise RuntimeError("요약 모델을 불러오는 데 너무 오래 걸립니다.")

    def close(self) -> None:
        _kill(self.proc)


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
