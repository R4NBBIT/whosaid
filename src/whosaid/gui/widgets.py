"""여러 화면에서 같이 쓰는 위젯."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from whosaid import audio, paths
from whosaid.audio import AUDIO_FILTER


class FilePicker(QWidget):
    """파일 선택 버튼 + 끌어다 놓기."""

    changed = Signal(str)

    def __init__(self, placeholder: str = "녹음 파일을 끌어다 놓거나 [파일 선택]을 누르세요") -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.path = ""
        self.label = QLabel(placeholder)
        self.label.setObjectName("dropLabel")
        self.label.setMinimumHeight(48)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn = QPushButton("파일 선택")
        btn.clicked.connect(self._browse)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label, 1)
        lay.addWidget(btn)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "녹음 파일 선택", "", AUDIO_FILTER + ";;모든 파일 (*)")
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> None:
        self.path = path
        self.label.setText(Path(path).name)
        self.changed.emit(path)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        urls = e.mimeData().urls()
        if urls:
            self.set_path(urls[0].toLocalFile())


class ProgressPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        self.reset()

    def reset(self, text: str = "") -> None:
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.msg.setText(text)

    def update_progress(self, stage: str, frac: float, msg: str) -> None:
        if frac < 0:
            self.bar.setRange(0, 0)  # 진행률을 모를 때 움직이는 막대
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(frac * 1000))
        self.msg.setText(msg)


class ClipPlayer:
    """화자 목소리 미리 듣기."""

    def __init__(self) -> None:
        self._player = None
        self._out = None

    def play(self, samples, start: float, end: float, key: str) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            return
        path = audio.save_wav(audio.cut(samples, start, end), paths.temp_dir() / f"preview_{key}.wav")
        if self._player is None:
            self._player = QMediaPlayer()
            self._out = QAudioOutput()
            self._player.setAudioOutput(self._out)
        self._player.stop()
        self._player.setSource(QUrl())
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    def stop(self) -> None:
        if self._player:
            self._player.stop()


class SpeakerTable(QTableWidget):
    """녹음 속 화자 목록. 들어보고 이름을 고르거나 새로 입력합니다."""

    COLS = ["화자", "말한 시간", "듣기", "이름", "판단 근거"]

    def __init__(self) -> None:
        super().__init__(0, len(self.COLS))
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().setVisible(False)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.player = ClipPlayer()
        self.analysis = None
        self._combos: dict[str, QComboBox] = {}

    def load(self, analysis, speakers, known_names: list[str], skip_unknown: bool = False) -> None:
        """speakers: 표시할 Speaker 목록. skip_unknown이면 모르는 화자의 기본 이름을 비워 둠."""
        self.analysis = analysis
        self._combos.clear()
        self.setRowCount(len(speakers))
        for row, sp in enumerate(speakers):
            voice = analysis.voices.get(sp.key)
            self.setItem(row, 0, _ro(sp.key))
            self.setItem(row, 1, _ro(audio.fmt_time(sp.seconds)))

            play = QPushButton("▶")
            play.setFixedWidth(40)
            play.setEnabled(bool(voice and voice.sample_spans))
            play.clicked.connect(lambda _=False, v=voice, k=sp.key: self._play(v, k))
            self.setCellWidget(row, 2, play)

            combo = QComboBox()
            combo.setEditable(True)
            combo.addItem("")
            combo.addItems(known_names)
            if sp.person_id:
                combo.setCurrentText(sp.name)
            elif not skip_unknown:
                combo.setCurrentText(sp.name)
            combo.lineEdit().setPlaceholderText("이름 입력 (비우면 건너뜀)")
            self._combos[sp.key] = combo
            self.setCellWidget(row, 3, combo)

            if sp.person_id:
                why = f"등록된 목소리와 {sp.score:.0%} 비슷함"
            elif sp.candidates:
                _, n, s = sp.candidates[0]
                why = f"처음 듣는 목소리 (가장 비슷한 사람: {n} {s:.0%})"
            else:
                why = "처음 듣는 목소리"
            self.setItem(row, 4, _ro(why))

    def _play(self, voice, key: str) -> None:
        if voice and voice.sample_spans and self.analysis is not None:
            s, e = voice.sample_spans[0]
            self.player.play(self.analysis.samples, s, e, key)

    def names(self) -> dict[str, str]:
        return {k: c.currentText().strip() for k, c in self._combos.items()}


def _ro(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item
