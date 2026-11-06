"""설정 화면."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from whosaid import models, paths, summarize
from whosaid.settings import Secrets, Settings
from whosaid.summarize.openai_compat import PRESETS


def _combo(items: dict[str, str]) -> QComboBox:
    c = QComboBox()
    for key, label in items.items():
        c.addItem(label, key)
    return c


def _select(combo: QComboBox, key: str) -> None:
    i = combo.findData(key)
    if i >= 0:
        combo.setCurrentIndex(i)


class SettingsTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self.window = window

        # ---- 음성 인식
        self.whisper = _combo(models.WHISPER_MODELS)
        self.language = _combo({"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어", "": "자동 감지"})
        self.glossary = QPlainTextEdit()
        self.glossary.setPlaceholderText("참석자 이름, 프로젝트명, 전문 용어를 쉼표로 적으면 인식이 정확해집니다.\n예: 김민수, 이지영, 와이어프레임, KPI")
        self.glossary.setMaximumHeight(70)
        self.threads = QSpinBox()
        self.threads.setRange(0, 64)
        self.threads.setSpecialValueText("자동")
        asr = QGroupBox("받아쓰기")
        f = QFormLayout(asr)
        f.addRow("음성 인식 모델", self.whisper)
        f.addRow("언어", self.language)
        f.addRow("용어 사전", self.glossary)
        f.addRow("CPU 스레드", self.threads)

        # ---- 화자 식별
        self.match = QDoubleSpinBox()
        self.match.setRange(0.2, 0.9)
        self.match.setSingleStep(0.05)
        self.match.setToolTip("높이면 확실할 때만 이름을 붙이고, 낮추면 더 적극적으로 붙입니다.")
        self.cluster = QDoubleSpinBox()
        self.cluster.setRange(0.2, 0.9)
        self.cluster.setSingleStep(0.05)
        self.cluster.setToolTip("한 사람이 여럿으로 나뉘면 높이고, 여러 사람이 하나로 합쳐지면 낮추세요.")
        self.learn = QCheckBox("회의록을 저장할 때 확인한 이름으로 목소리 보강 (기본값)")
        spk = QGroupBox("발언자 식별")
        f = QFormLayout(spk)
        f.addRow("이름 붙이는 기준 (유사도)", self.match)
        f.addRow("목소리 구분 기준", self.cluster)
        f.addRow(self.learn)

        # ---- 요약
        self.summarizer = _combo(summarize.LABELS)
        self.summarizer.currentIndexChanged.connect(self._toggle)
        self.local_model = _combo({k: m.label for k, m in models.LOCAL_LLMS.items()})
        self.local_accel = _combo({"cpu": "CPU (안정적)", "vulkan": "GPU 가속 - Vulkan (인텔 Arc 등, 실험적)"})
        self.anthropic_key = QLineEdit()
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key.setPlaceholderText("sk-ant-...")
        self.anthropic_model = QLineEdit()
        self.openai_preset = QComboBox()
        self.openai_preset.addItem("직접 입력", "")
        for label, url in PRESETS.items():
            self.openai_preset.addItem(label, url)
        self.openai_preset.currentIndexChanged.connect(
            lambda: self.openai_preset.currentData() and self.openai_url.setText(self.openai_preset.currentData()))
        self.openai_url = QLineEdit()
        self.openai_model = QLineEdit()
        self.openai_model.setPlaceholderText("사용할 모델 이름 (각 서비스 문서 참고)")
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setPlaceholderText("Ollama는 비워 두세요")

        self.local_box = QGroupBox("PC 안에서 처리")
        f = QFormLayout(self.local_box)
        f.addRow("모델", self.local_model)
        f.addRow("처리 장치", self.local_accel)
        f.addRow(QLabel("처음 쓸 때 모델을 한 번 내려받습니다. 회의 내용이 PC 밖으로 나가지 않습니다."))
        self.anthropic_box = QGroupBox("Claude API")
        f = QFormLayout(self.anthropic_box)
        f.addRow("API 키", self.anthropic_key)
        f.addRow("모델", self.anthropic_model)
        f.addRow(QLabel("요약할 때 녹음이 아닌 대본(텍스트)만 전송됩니다."))
        self.openai_box = QGroupBox("OpenAI 호환 API")
        f = QFormLayout(self.openai_box)
        f.addRow("서비스", self.openai_preset)
        f.addRow("주소", self.openai_url)
        f.addRow("모델", self.openai_model)
        f.addRow("API 키", self.openai_key)
        f.addRow(QLabel("요약할 때 녹음이 아닌 대본(텍스트)만 전송됩니다. Ollama는 PC 안에서 처리됩니다."))

        summ = QGroupBox("회의록 요약")
        sl = QVBoxLayout(summ)
        f = QFormLayout()
        f.addRow("요약 방식", self.summarizer)
        sl.addLayout(f)
        sl.addWidget(self.local_box)
        sl.addWidget(self.anthropic_box)
        sl.addWidget(self.openai_box)

        # ---- 저장
        self.output = QLineEdit()
        browse = QPushButton("찾아보기")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.output, 1)
        row.addWidget(browse)
        data_btn = QPushButton("프로그램 데이터 폴더 열기 (목소리 지문·모델)")
        data_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        store = QGroupBox("저장")
        f = QFormLayout(store)
        f.addRow("회의록 저장 폴더", row)
        f.addRow(data_btn)

        save = QPushButton("설정 저장")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(save)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        for w in (asr, spk, summ, store):
            lay.addWidget(w)
        lay.addLayout(bottom)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.load()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "회의록 저장 폴더", self.output.text())
        if d:
            self.output.setText(d)

    def _toggle(self) -> None:
        kind = self.summarizer.currentData()
        self.local_box.setVisible(kind == "local")
        self.anthropic_box.setVisible(kind == "anthropic")
        self.openai_box.setVisible(kind == "openai")

    def load(self) -> None:
        s = self.window.engine.settings
        sec = Secrets.load()
        _select(self.whisper, s.whisper_model)
        _select(self.language, s.language)
        self.glossary.setPlainText(s.glossary)
        self.threads.setValue(s.cpu_threads)
        self.match.setValue(s.match_threshold)
        self.cluster.setValue(s.cluster_threshold)
        self.learn.setChecked(s.learn_from_meetings)
        _select(self.summarizer, s.summarizer)
        _select(self.local_model, s.local_model)
        _select(self.local_accel, s.local_accel)
        self.anthropic_model.setText(s.anthropic_model)
        self.anthropic_key.setText(sec.anthropic_api_key)
        self.openai_url.setText(s.openai_base_url)
        self.openai_model.setText(s.openai_model)
        self.openai_key.setText(sec.openai_api_key)
        self.output.setText(str(s.resolved_output_dir()))
        self._toggle()

    def save(self) -> None:
        s = Settings(
            whisper_model=self.whisper.currentData(),
            language=self.language.currentData(),
            glossary=self.glossary.toPlainText().strip(),
            cpu_threads=self.threads.value(),
            cluster_threshold=round(self.cluster.value(), 3),
            match_threshold=round(self.match.value(), 3),
            learn_from_meetings=self.learn.isChecked(),
            summarizer=self.summarizer.currentData(),
            local_model=self.local_model.currentData(),
            local_accel=self.local_accel.currentData(),
            local_context=self.window.engine.settings.local_context,
            anthropic_model=self.anthropic_model.text().strip(),
            openai_base_url=self.openai_url.text().strip(),
            openai_model=self.openai_model.text().strip(),
            output_dir=self.output.text().strip(),
        )
        s.save()
        sec = Secrets.load()
        sec.anthropic_api_key = self.anthropic_key.text().strip()
        sec.openai_api_key = self.openai_key.text().strip()
        sec.save()
        self.window.apply_settings(s)
        QMessageBox.information(self, "WhoSaid", "설정을 저장했습니다.")
