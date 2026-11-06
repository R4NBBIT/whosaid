"""명령줄 사용법.

    whosaid enroll 녹음.m4a          # 녹음 속 화자에게 이름을 붙여 목소리 등록
    whosaid process 회의.m4a         # 회의록 만들기
    whosaid people                   # 등록된 사람 보기
    whosaid download                 # 필요한 모델 미리 받기
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whosaid import audio, paths
from whosaid.audio import fmt_time


def _progress(stage, frac, msg):
    pct = f"{frac * 100:5.1f}% " if frac is not None else "       "
    print(f"\r{pct}{msg:<60}", end="", file=sys.stderr, flush=True)


def cmd_people(args) -> int:
    from whosaid.voiceprints import VoiceprintStore

    store = VoiceprintStore()
    if store.stale_model:
        print("※ 예전 모델로 만든 목소리 지문이 있어 다시 등록이 필요합니다.")
    people = store.people()
    if not people:
        print("등록된 사람이 없습니다. 'whosaid enroll 녹음파일'로 등록하세요.")
    for p in people:
        print(f"- {p.name}: 목소리 조각 {p.samples}개, {p.seconds:.0f}초")
    print(f"\n저장 위치: {store.root}")
    return 0


def _ask_names(engine, analysis) -> dict[str, str]:
    clip_dir = paths.temp_dir()
    names = {}
    print("\n녹음에서 찾은 목소리:")
    for sp in analysis.speakers:
        voice = analysis.voices[sp.key]
        clip = None
        if voice.sample_spans:
            s, e = voice.sample_spans[0]
            clip = audio.save_wav(audio.cut(analysis.samples, s, e), clip_dir / f"sample_{sp.key}.wav")
        guess = sp.name if sp.person_id else ""
        print(f"\n[{sp.key}] 말한 시간 {sp.seconds:.0f}초, 처음 등장 {fmt_time(voice.sample_spans[0][0]) if voice.sample_spans else '-'}")
        if clip:
            print(f"   들어보기: {clip}")
        if sp.candidates:
            print("   비슷한 사람: " + ", ".join(f"{n}({s:.2f})" for _, n, s in sp.candidates))
        hint = f" [엔터={guess}]" if guess else " [엔터=건너뛰기]"
        answer = input(f"   이름{hint}: ").strip()
        names[sp.key] = answer or guess
    return names


def cmd_enroll(args) -> int:
    from whosaid.pipeline import Engine

    engine = Engine()
    analysis = engine.analyze(args.file, args.speakers, _progress)
    print(file=sys.stderr)
    names = _ask_names(engine, analysis)
    learned = engine.learn(analysis, names)
    print("\n등록/보강한 사람: " + (", ".join(learned) if learned else "없음"))
    return 0


def cmd_process(args) -> int:
    from whosaid.pipeline import Engine, save_result

    engine = Engine()
    if args.no_summary:
        engine.settings.summarizer = "none"
    analysis, result = engine.process(args.file, args.speakers, not args.no_summary, _progress)
    print(file=sys.stderr)
    print("\n화자: " + ", ".join(f"{s.key}={s.name}({s.score:.2f})" for s in result.speakers))
    if args.confirm:
        names = _ask_names(engine, analysis)
        for sp in result.speakers:
            if names.get(sp.key):
                sp.name = names[sp.key]
        if engine.settings.learn_from_meetings:
            engine.learn(analysis, names)
    out = Path(args.out) if args.out else engine.settings.resolved_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    md = save_result(result, out, args.title or "")
    print(f"\n저장했습니다: {md}")
    return 0


def cmd_download(args) -> int:
    from whosaid import models
    from whosaid.settings import Settings

    s = Settings.load()
    models.segmentation_model(_progress)
    models.embedding_model(_progress)
    from whosaid.transcribe import Transcriber

    Transcriber(s.whisper_model, s.threads(), _progress)
    if s.summarizer == "local" or args.llm:
        models.llama_server(s.local_accel, _progress)
        models.local_llm(s.local_model, _progress)
    print("\n모델 준비 완료:", paths.models_dir())
    return 0


def cmd_selftest(args) -> int:
    """설치가 제대로 됐는지 전 과정을 한 번 돌려 봅니다 (CI와 문제 진단용)."""
    import time

    from whosaid.pipeline import Engine
    from whosaid.settings import Settings
    from whosaid.voiceprints import VoiceprintStore

    t0 = time.time()
    s = Settings.load()
    s.whisper_model = args.whisper or s.whisper_model
    s.language = args.language if args.language is not None else s.language
    if args.llm:
        s.summarizer, s.local_model, s.local_context = "local", args.llm, 4096
    else:
        s.summarizer = "none"
    store = VoiceprintStore(paths.temp_dir() / "selftest-voiceprints")
    for p in store.people():
        store.delete(p.id)
    engine = Engine(s, store)

    a = engine.analyze(args.audio, progress=_progress)
    print(f"\n[1] 화자 분리: 목소리 {len(a.speakers)}개")
    names = {sp.key: f"테스트{sp.key}" for sp in a.speakers}
    engine.learn(a, names)
    again = engine.analyze(args.audio, samples=a.samples)
    hits = sum(sp.name == names[sp.key] for sp in again.speakers)
    print(f"[2] 목소리 등록 후 식별: {hits}/{len(again.speakers)}")
    if hits != len(again.speakers):
        print("실패: 등록한 목소리를 다시 찾지 못했습니다.")
        return 1

    analysis, result = engine.process(args.audio, progress=_progress, do_summary=bool(args.llm), )
    print(f"\n[3] 받아쓰기: 발화 {len(result.utterances)}개")
    print(result.transcript_text()[:800])
    if not result.utterances:
        print("실패: 받아쓴 내용이 없습니다.")
        return 1
    if args.llm:
        print(f"\n[4] 요약:\n{result.summary[:800]}")
        if not result.summary or result.summary.startswith("> 요약을 만들지 못했습니다"):
            print("실패: 요약을 만들지 못했습니다.")
            return 1
    if "onnxruntime" in sys.modules:
        print("실패: onnxruntime 패키지가 함께 로드되었습니다(윈도우 DLL 충돌 위험).")
        return 1
    print(f"\n자체 점검 통과 ({time.time() - t0:.0f}초)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whosaid", description="누가 말했는지 알아보는 회의록 프로그램")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("people", help="등록된 사람 보기")
    p.set_defaults(func=cmd_people)

    p = sub.add_parser("enroll", help="녹음으로 목소리 등록")
    p.add_argument("file")
    p.add_argument("--speakers", type=int, help="녹음 속 사람 수 (알면 정확해짐)")
    p.set_defaults(func=cmd_enroll)

    p = sub.add_parser("process", help="회의록 만들기")
    p.add_argument("file")
    p.add_argument("--speakers", type=int, help="참석자 수 (알면 정확해짐)")
    p.add_argument("--title", help="회의 제목")
    p.add_argument("--out", help="저장 폴더")
    p.add_argument("--no-summary", action="store_true", help="요약 없이 대본만")
    p.add_argument("--confirm", action="store_true", help="저장 전에 화자 이름 확인/수정")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("download", help="모델 미리 받기")
    p.add_argument("--llm", action="store_true", help="요약 모델도 받기")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("selftest", help="설치 점검: 녹음 하나로 전 과정을 돌려 봄")
    p.add_argument("audio")
    p.add_argument("--whisper", help="음성 인식 모델 (예: tiny)")
    p.add_argument("--language", help="언어 코드 (예: ko, zh)")
    p.add_argument("--llm", help="요약까지 점검할 내장 모델 (예: qwen2.5-3b)")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("gui", help="화면으로 실행")
    p.set_defaults(func=lambda a: __import__("whosaid.gui.app", fromlist=["main"]).main())

    for stream in (sys.stdout, sys.stderr):  # 출력이 파이프로 갈 때도 한글이 오류 나지 않게
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n취소했습니다.", file=sys.stderr)
        return 130
