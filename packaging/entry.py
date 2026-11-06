"""PyInstaller 실행 파일 시작점. 인자가 있으면 명령줄, 없으면 화면으로 실행합니다."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # 창 모드 실행 파일에는 콘솔이 없어 stdout/stderr가 None입니다.
    # 진행 표시줄 등을 출력하는 라이브러리가 멈추지 않도록 로그 파일로 돌립니다.
    if sys.stdout is None or sys.stderr is None:
        from whosaid import paths

        log = open(paths.temp_dir() / "whosaid.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    if len(sys.argv) > 1:
        from whosaid.cli import main
    else:
        from whosaid.gui.app import main
    sys.exit(main())
