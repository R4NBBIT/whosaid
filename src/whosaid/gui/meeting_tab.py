"""회의록 만들기 화면."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from whosaid import summarize
from whosaid.gui.widgets import FilePicker, ProgressPanel, SpeakerTable
from whosaid.gui.worker import Task
from whosaid.pipeline import apply_names, save_result


class MeetingTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.task: Task | None = None
        self.analysis = None
        self.result = None
        self.saved_path = None
        self._learned = False

        # ---- 입력
        self.picker = FilePicker()
        self.title = QLineEdit()
        self.title.setPlaceholderText("비우면 파일 이름을 씁니다 (예: 주간회의)")
        self.num = QSpinBox()
        self.num.setRange(0, 20)
        self.num.setSpecialValueText("자동")
        self.do_summary = QCheckBox()
        self.start_btn = QPushButton("회의록 만들기")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)

        form = QVBoxLayout()
        form.addWidget(self.picker)
        row = QHBoxLayout()
        row.addWidget(QLabel("회의 제목"))
        row.addWidget(self.title, 2)
        row.addWidget(QLabel("참석자 수"))
        row.addWidget(self.num)
        form.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.do_summary, 1)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.start_btn)
        form.addLayout(row)
        self.progress = ProgressPanel()
        form.addWidget(self.progress)
        top = QGroupBox("1. 녹음 넣기")
        top.setLayout(form)

        # ---- 결과
        self.table = SpeakerTable()
        self.table.setMinimumHeight(150)
        self.learn = QCheckBox("확인한 이름으로 목소리를 학습해 다음 회의 정확도 높이기")
        self.learn.setChecked(True)
        apply_btn = QPushButton("이름 반영")
        apply_btn.clicked.connect(self.apply_names)
        self.resum_btn = QPushButton("요약 다시 만들기")
        self.resum_btn.clicked.connect(self.resummarize)
        self.save_btn = QPushButton("저장")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self.save)
        self.open_btn = QPushButton("저장 폴더 열기")
        self.open_btn.clicked.connect(self.open_folder)

        spk_box = QGroupBox("2. 발언자 확인 — ▶로 들어보고 이름이 틀리면 고치세요")
        spk_lay = QVBoxLayout(spk_box)
        spk_lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(self.learn, 1)
        row.addWidget(apply_btn)
        spk_lay.addLayout(row)

        self.minutes = QTextBrowser()
        self.minutes.setOpenExternalLinks(True)
        self.script = QPlainTextEdit()
        self.script.setReadOnly(True)
        views = QTabWidget()
        views.addTab(self.minutes, "회의록")
        views.addTab(self.script, "대본")

        out_box = QGroupBox("3. 결과")
        out_lay = QVBoxLayout(out_box)
        out_lay.addWidget(views)
        row = QHBoxLayout()
        self.saved_label = QLabel("")
        row.addWidget(self.saved_label, 1)
        row.addWidget(self.resum_btn)
        row.addWidget(self.open_btn)
        row.addWidget(self.save_btn)
        out_lay.addLayout(row)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(spk_box)
        split.addWidget(out_box)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([280, 520])
        self.results = split
        self.results.setEnabled(False)

        lay = QVBoxLayout(self)
        lay.addWidget(top)
        lay.addWidget(split, 1)
        self.refresh_settings()

    # ------------------------------------------------------------------
    def refresh_settings(self) -> None:
        kind = self.window.engine.settings.summarizer
        self.do_summary.setText(f"회의록 요약 만들기 — {summarize.LABELS.get(kind, kind)}")
        self.do_summary.setChecked(kind != "none")
        self.do_summary.setEnabled(kind != "none")
        self.resum_btn.setEnabled(kind != "none")

    def set_busy(self, busy: bool) -> None:
        self.start_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.results.setEnabled(not busy and self.result is not None)
        self.window.set_busy(busy)

    def start(self) -> None:
        path = self.picker.path
        if not path:
            QMessageBox.information(self, "WhoSaid", "녹음 파일을 먼저 골라 주세요.")
            return
        if self.window.busy:
            return
        engine = self.window.engine
        n = self.num.value() or None
        do_summary = self.do_summary.isChecked()
        self.result = None
        self.saved_path = None
        self.saved_label.setText("")
        self.progress.reset("시작하는 중…")
        self.task = Task(lambda p, c: engine.process(path, n, do_summary, p, c), self)
        self.task.progressed.connect(self.progress.update_progress)
        self.task.succeeded.connect(self._done)
        self.task.failed.connect(self._failed)
        self.task.cancelled.connect(self._cancelled)
        self.set_busy(True)
        self.task.start()

    def cancel(self) -> None:
        if self.task:
            self.task.cancel()
            self.progress.msg.setText("취소하는 중…")

    def _done(self, value) -> None:
        self.analysis, self.result = value
        self._learned = False
        self.progress.update_progress("done", 1.0, "완료! 발언자 이름을 확인하고 저장하세요.")
        known = [p.name for p in self.window.engine.store.people()]
        self.table.load(self.analysis, self.result.speakers, known)
        self.render()
        self.set_busy(False)
        self.window.people_tab.reload()

    def _failed(self, msg: str) -> None:
        self.progress.reset("")
        self.set_busy(False)
        QMessageBox.warning(self, "WhoSaid", f"처리하지 못했습니다.\n\n{msg}")

    def _cancelled(self) -> None:
        self.progress.reset("취소했습니다.")
        self.set_busy(False)

    # ------------------------------------------------------------------
    def render(self) -> None:
        if not self.result:
            return
        self.minutes.setMarkdown(self.result.to_markdown(self.title.text().strip()))
        self.script.setPlainText(self.result.transcript_text())

    def apply_names(self) -> dict[str, str]:
        if not self.result:
            return {}
        learn_names = apply_names(self.result, self.analysis, self.table.names())
        self.render()
        return learn_names

    def resummarize(self) -> None:
        if not self.result or self.window.busy:
            return
        self.apply_names()
        engine, result = self.window.engine, self.result
        self.progress.reset("요약 다시 만드는 중…")
        self.task = Task(lambda p, c: engine.summarize(result, p, c), self)
        self.task.progressed.connect(self.progress.update_progress)
        self.task.succeeded.connect(lambda _: (self.progress.update_progress("done", 1.0, "요약 완료"),
                                               self.render(), self.set_busy(False)))
        self.task.failed.connect(self._failed)
        self.task.cancelled.connect(self._cancelled)
        self.set_busy(True)
        self.task.start()

    def save(self) -> None:
        if not self.result:
            return
        engine = self.window.engine
        learn_names = self.apply_names()
        learned = []
        if self.learn.isChecked() and not self._learned:
            learned = engine.learn(self.analysis, learn_names)
            self._learned = True  # 같은 회의로 두 번 학습하지 않게
            self.window.people_tab.reload()
        out = engine.settings.resolved_output_dir()
        self.saved_path = save_result(self.result, out, self.title.text().strip())
        msg = f"저장했습니다: {self.saved_path.name}"
        if learned:
            msg += f"  ·  목소리 학습: {', '.join(learned)}"
        self.saved_label.setText(msg)

    def open_folder(self) -> None:
        out = self.window.engine.settings.resolved_output_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
