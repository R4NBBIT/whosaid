"""참석자 목소리 등록 화면."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QVBoxLayout, QWidget,
)

from whosaid.gui.widgets import FilePicker, ProgressPanel, SpeakerTable, _ro
from whosaid.gui.worker import Task

HELP = (
    "참석자들이 대화한 녹음 하나만 있으면 됩니다. [목소리 찾기]를 누르면 녹음 속 목소리를 사람별로 나눠 줍니다.\n"
    "▶로 들어보고 이름을 적은 뒤 [등록]을 누르세요. 한 사람당 30초~2분 정도 말한 녹음이면 충분하고,\n"
    "회의록을 만들 때마다 확인한 결과로 계속 보강됩니다."
)


class PeopleTab(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.task: Task | None = None
        self.analysis = None

        # ---- 등록된 사람
        self.people = QTableWidget(0, 3)
        self.people.setHorizontalHeaderLabels(["이름", "목소리 조각", "학습한 길이"])
        self.people.verticalHeader().setVisible(False)
        self.people.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.people.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.people.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        rename = QPushButton("이름 바꾸기")
        rename.clicked.connect(self.rename)
        reset = QPushButton("목소리 초기화")
        reset.clicked.connect(self.reset)
        delete = QPushButton("삭제")
        delete.clicked.connect(self.delete)
        self.stale = QLabel("")
        self.stale.setWordWrap(True)
        left = QGroupBox("등록된 사람")
        ll = QVBoxLayout(left)
        ll.addWidget(self.people)
        row = QHBoxLayout()
        row.addWidget(rename)
        row.addWidget(reset)
        row.addWidget(delete)
        ll.addLayout(row)
        ll.addWidget(self.stale)

        # ---- 녹음으로 등록
        self.picker = FilePicker()
        self.num = QSpinBox()
        self.num.setRange(0, 20)
        self.num.setSpecialValueText("자동")
        self.find_btn = QPushButton("목소리 찾기")
        self.find_btn.setObjectName("primary")
        self.find_btn.clicked.connect(self.analyze)
        self.progress = ProgressPanel()
        self.table = SpeakerTable()
        self.enroll_btn = QPushButton("등록")
        self.enroll_btn.setObjectName("primary")
        self.enroll_btn.setEnabled(False)
        self.enroll_btn.clicked.connect(self.enroll)

        right = QGroupBox("녹음으로 목소리 등록")
        rl = QVBoxLayout(right)
        help_label = QLabel(HELP)
        help_label.setWordWrap(True)
        rl.addWidget(help_label)
        form = QFormLayout()
        form.addRow("녹음 파일", self.picker)
        form.addRow("녹음 속 사람 수", self.num)
        rl.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.find_btn)
        rl.addLayout(row)
        rl.addWidget(self.progress)
        rl.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.enroll_btn)
        rl.addLayout(row)

        lay = QHBoxLayout(self)
        lay.addWidget(left, 2)
        lay.addWidget(right, 3)
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        store = self.window.engine.store
        people = store.people()
        self.people.setRowCount(len(people))
        for r, p in enumerate(people):
            item = _ro(p.name)
            item.setData(256, p.id)
            self.people.setItem(r, 0, item)
            self.people.setItem(r, 1, _ro(f"{p.samples}개"))
            self.people.setItem(r, 2, _ro(f"{p.seconds / 60:.1f}분" if p.seconds >= 60 else f"{p.seconds:.0f}초"))
        self.stale.setText(
            "※ 예전 버전의 목소리 지문이 있어 다시 등록이 필요합니다." if store.stale_model else "")

    def _selected(self):
        items = self.people.selectedItems()
        if not items:
            QMessageBox.information(self, "WhoSaid", "목록에서 사람을 먼저 고르세요.")
            return None
        return self.people.item(items[0].row(), 0).data(256)

    def rename(self) -> None:
        pid = self._selected()
        if not pid:
            return
        store = self.window.engine.store
        name, ok = QInputDialog.getText(self, "이름 바꾸기", "새 이름", text=store.get(pid).name)
        if ok and name.strip():
            try:
                store.rename(pid, name)
            except ValueError as e:
                QMessageBox.warning(self, "WhoSaid", str(e))
            self.reload()

    def reset(self) -> None:
        pid = self._selected()
        if not pid:
            return
        store = self.window.engine.store
        if QMessageBox.question(self, "WhoSaid", f"{store.get(pid).name}의 학습한 목소리를 지울까요? 이름은 남습니다.") \
                == QMessageBox.StandardButton.Yes:
            store.reset_samples(pid)
            self.reload()

    def delete(self) -> None:
        pid = self._selected()
        if not pid:
            return
        store = self.window.engine.store
        if QMessageBox.question(self, "WhoSaid", f"{store.get(pid).name}을(를) 삭제할까요?") \
                == QMessageBox.StandardButton.Yes:
            store.delete(pid)
            self.reload()

    # ------------------------------------------------------------------
    def analyze(self) -> None:
        path = self.picker.path
        if not path:
            QMessageBox.information(self, "WhoSaid", "녹음 파일을 먼저 골라 주세요.")
            return
        if self.window.busy:
            return
        engine = self.window.engine
        n = self.num.value() or None
        self.progress.reset("시작하는 중…")
        self.enroll_btn.setEnabled(False)
        self.task = Task(lambda p, c: engine.analyze(path, n, p, c), self)
        self.task.progressed.connect(self.progress.update_progress)
        self.task.succeeded.connect(self._analyzed)
        self.task.failed.connect(self._failed)
        self.task.cancelled.connect(lambda: self._failed("취소했습니다."))
        self.find_btn.setEnabled(False)
        self.window.set_busy(True)
        self.task.start()

    def _analyzed(self, analysis) -> None:
        self.analysis = analysis
        known = [p.name for p in self.window.engine.store.people()]
        self.table.load(analysis, analysis.speakers, known, skip_unknown=True)
        self.progress.update_progress("done", 1.0,
                                      f"목소리 {len(analysis.speakers)}개를 찾았습니다. 들어보고 이름을 적어 주세요.")
        self.enroll_btn.setEnabled(True)
        self.find_btn.setEnabled(True)
        self.window.set_busy(False)

    def _failed(self, msg: str) -> None:
        self.progress.reset("")
        self.find_btn.setEnabled(True)
        self.window.set_busy(False)
        QMessageBox.warning(self, "WhoSaid", msg)

    def enroll(self) -> None:
        if not self.analysis:
            return
        names = self.table.names()
        filled = [n for n in names.values() if n]
        if len(filled) != len(set(filled)):
            if QMessageBox.question(
                self, "WhoSaid",
                "같은 이름이 여러 목소리에 붙어 있습니다. 한 사람이 둘로 나뉜 경우라면 괜찮습니다. 계속할까요?",
            ) != QMessageBox.StandardButton.Yes:
                return
        learned = self.window.engine.learn(self.analysis, names)
        self.reload()
        self.enroll_btn.setEnabled(False)
        self.progress.reset(("등록했습니다: " + ", ".join(dict.fromkeys(learned))) if learned
                            else "이름을 적은 목소리가 없어 등록하지 않았습니다.")
