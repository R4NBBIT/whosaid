#!/usr/bin/env python3
"""커밋 전 개인정보 검사 훅을 켭니다. 레포를 받은 뒤 한 번만 실행하세요.

    python scripts/install_hooks.py
"""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=root, check=True)
hook = root / ".githooks" / "pre-commit"
if sys.platform != "win32":
    hook.chmod(0o755)
print("커밋 전 개인정보 검사 훅을 켰습니다 (.githooks/pre-commit).")
