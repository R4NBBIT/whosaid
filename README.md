# WhoSaid — 누가 말했나

회의 녹음을 텍스트로 바꾸고, **미리 등록한 목소리로 발언자를 식별해** 회의록까지 만들어 주는 윈도우용 로컬 프로그램입니다.

일반 회의록 서비스는 녹음마다 "화자1, 화자2"로 나누기만 해서 매번 이름을 다시 붙여야 합니다. WhoSaid는 팀원 목소리를 한 번 등록해 두면 매주 회의에서 **이름을 자동으로 붙이고**, 확인한 결과로 계속 학습합니다.

- 🎙️ 녹음 하나로 참석자 목소리 등록 (한 사람당 30초~2분이면 충분)
- 🧑‍🤝‍🧑 매 회의마다 발언자 자동 식별, 처음 듣는 목소리는 "참석자 N"으로 표시
- 📝 받아쓰기 + 회의록 요약 (회의 요약, 결정 사항, 할 일, 미결 사항)
- 🔒 음성 처리는 전부 내 PC 안에서. 요약도 PC 안에서 처리할 수 있음

## 설치

1. [Releases](https://github.com/R4NBBIT/whosaid/releases)에서 `WhoSaid-Setup-버전.exe`를 받아 실행합니다. (관리자 권한 필요 없음)
2. 처음 실행하면 필요한 AI 모델을 한 번 내려받습니다.
   - 화자 분리·목소리 지문 모델: 약 35MB
   - 음성 인식 모델: 약 1.6GB (`large-v3-turbo` 기준)
   - 내장 요약 모델: 약 4.7GB (PC 안에서 요약할 때만)

권장 사양: Windows 10/11 64비트, RAM 16GB (8GB면 설정에서 가벼운 모델 선택). 그래픽카드는 없어도 됩니다.

## 사용법

### 1. 참석자 목소리 등록 (처음 한 번)
1. **참석자 목소리 등록** 탭에서 참석자들이 대화한 녹음을 넣고 **목소리 찾기**를 누릅니다.
2. 녹음 속 목소리가 사람별로 나뉩니다. **▶**로 들어보고 이름을 적은 뒤 **등록**을 누릅니다.

### 2. 매주 회의록 만들기
1. **회의록 만들기** 탭에 회의 녹음을 넣고 **회의록 만들기**를 누릅니다.
2. 끝나면 발언자 이름을 확인합니다. 틀린 이름은 고치고 **저장**을 누릅니다.
3. 저장할 때 확인한 이름으로 목소리를 보강 학습합니다. 쓸수록 정확해져요.

회의록은 `문서\WhoSaid` 폴더에 마크다운(`.md`)으로 저장됩니다.

### 정확도를 높이는 팁
- **참석자 수**를 알면 입력하세요. 목소리 구분이 정확해집니다.
- **설정 → 용어 사전**에 참석자 이름, 프로젝트명, 전문 용어를 적으면 받아쓰기가 정확해집니다.
- 마이크를 회의 테이블 가운데에 두세요. 녹음 품질이 가장 큰 영향을 줍니다.
- 여러 사람이 동시에 말한 구간은 정확도가 떨어집니다.

## 요약 방식

**설정 → 회의록 요약**에서 고릅니다.

| 방식 | 설명 | 외부로 나가는 것 |
|---|---|---|
| PC 안에서 처리 (기본) | 내장 모델(Qwen2.5)로 요약. 추가 설치 없음 | 없음 |
| Claude API | Anthropic API 키 필요 | 대본(텍스트)만 |
| OpenAI 호환 API | OpenAI, Google Gemini, Ollama 등 | 대본(텍스트)만. Ollama는 PC 안 |
| 요약 안 함 | 대본만 저장 | 없음 |

인텔 Arc 등 GPU가 있다면 **처리 장치 → Vulkan(실험적)**으로 요약을 빠르게 할 수 있습니다.

## 개인정보

- 녹음 원본은 저장하지 않습니다. 목소리 지문은 녹음에서 뽑은 숫자 벡터만 저장합니다.
- 모든 데이터는 내 PC에만 있습니다.
  - 목소리 지문·설정·모델: `%APPDATA%\WhoSaid`
  - 회의록: `문서\WhoSaid` (설정에서 변경 가능)
- 목소리는 생체정보에 해당할 수 있으니, **등록 전에 팀원들의 동의를 받으세요.**
- 프로그램을 제거해도 위 데이터는 남습니다. 지우려면 폴더를 직접 삭제하세요.

## 동작 방식

```
녹음 ─▶ 화자 분리 (pyannote segmentation 3.0, sherpa-onnx)
     ─▶ 목소리 지문 추출 (3D-Speaker CAM++) ─▶ 등록된 사람과 비교 (코사인 유사도)
     ─▶ 받아쓰기 (faster-whisper, 말소리 구간만) ─▶ 단어마다 발언자 연결
     ─▶ 회의록 요약 (llama.cpp 내장 모델 또는 API)
```

녹음 속 화자마다 목소리 지문의 평균을 내고, 등록된 사람과 가장 비슷한 짝부터 1:1로 연결합니다. 기준(기본 0.5)보다 덜 비슷하면 이름을 붙이지 않습니다. 한 사람이 둘로 나뉜 경우에는 두 화자가 모두 그 사람과 충분히 비슷할 때만 합칩니다.

## 개발

```bash
git clone https://github.com/R4NBBIT/whosaid
cd whosaid
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[gui,dev]"
python scripts/install_hooks.py                      # 커밋 전 개인정보 검사 켜기 (필수)

whosaid gui                                          # 화면 실행
whosaid enroll 녹음.m4a                               # 명령줄로 목소리 등록
whosaid process 회의.m4a --title 주간회의 --confirm    # 명령줄로 회의록 만들기
pytest                                               # 테스트
```

실제 모델로 하는 통합 테스트는 `bash scripts/fetch_test_models.sh /tmp/models` 후 `WHOSAID_TEST_MODELS=/tmp/models pytest`로 실행합니다.

윈도우 설치 파일은 `v0.1.0` 같은 태그를 올리면 GitHub Actions가 만들어 Releases에 올립니다.

### ⚠️ 이 레포는 공개(Public)입니다
회의 녹음, 목소리 지문, 회의록, 모델 파일, API 키는 **절대 커밋하지 마세요.** 세 겹으로 막고 있습니다.
1. `.gitignore`가 오디오·지문·모델·결과물을 제외
2. 커밋 전 훅(`scripts/check_private_data.py --staged`)이 확장자를 바꾼 녹음, 코드 속 API 키까지 검사
3. CI가 레포 전체를 다시 검사

프로그램 자체도 모든 데이터를 레포 밖(`%APPDATA%`, `문서`)에 저장합니다.

## 사용한 오픈소스와 모델

| 구성 요소 | 라이선스 |
|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / Whisper 모델 | MIT |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Apache-2.0 |
| pyannote segmentation 3.0 | MIT |
| 3D-Speaker CAM++ | Apache-2.0 |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT |
| Qwen2.5 Instruct | Apache-2.0 |
| PySide6 (Qt) | LGPL-3.0 |
