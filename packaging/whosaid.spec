# -*- mode: python ; coding: utf-8 -*-
# 윈도우용 WhoSaid 빌드:  pyinstaller packaging/whosaid.spec --noconfirm
# AI 모델은 포함하지 않습니다(처음 실행 때 사용자 PC에 내려받음).

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = [], [], []
for pkg in ("sherpa_onnx", "ctranslate2"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("faster_whisper")
hiddenimports += ["whosaid.gui.meeting_tab", "whosaid.gui.people_tab", "whosaid.gui.settings_tab",
                  "whosaid.summarize.local_llama", "whosaid.summarize.anthropic_api",
                  "whosaid.summarize.openai_compat"]

a = Analysis(
    ["entry.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # onnxruntime 패키지는 sherpa-onnx의 onnxruntime.dll과 충돌할 수 있어 넣지 않음
    excludes=["onnxruntime", "torch", "tensorflow", "matplotlib", "tkinter", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhoSaid",
    console=False,
    icon=None,
)
# 같은 폴더에 명령줄용 실행 파일도 함께 둡니다 (whosaid-cli.exe process 회의.m4a)
cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="whosaid-cli",
    console=True,
    icon=None,
)
coll = COLLECT(exe, cli, a.binaries, a.datas, strip=False, upx=False, name="WhoSaid")
