#!/usr/bin/env bash
# 테스트용 화자 분리 모델과 sherpa-onnx 공개 예제 녹음을 지정한 폴더(레포 밖)에 받습니다.
# 사용법: bash scripts/fetch_test_models.sh /tmp/models
set -euo pipefail
dest="${1:?저장할 폴더를 지정하세요}"
mkdir -p "$dest"
cd "$dest"
base=https://github.com/k2-fsa/sherpa-onnx/releases/download
if [ ! -f sherpa-onnx-pyannote-segmentation-3-0/model.onnx ]; then
  curl -sSL -o seg.tar.bz2 "$base/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
  tar xjf seg.tar.bz2
  rm seg.tar.bz2
fi
[ -f 3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx ] || \
  curl -sSLO "$base/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
[ -f 0-four-speakers-zh.wav ] || curl -sSLO "$base/speaker-segmentation-models/0-four-speakers-zh.wav"
ls -la
