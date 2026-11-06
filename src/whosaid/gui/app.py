"""WhoSaid 데스크톱 프로그램 시작점."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from whosaid import APP_NAME, __version__
from whosaid.pipeline import Engine

STYLE = """
QWidget { font-size: 10pt; }
QGroupBox { font-weight: 600; border: 1px solid #d0d4da; border-radius: 6px; margin-top: 10px; padding: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLabel#dropLabel { border: 2px dashed #b8bec7; border-radius: 6px; color: #5b6470; padding: 6px; }
QPushButton { padding: 5px 12px; }
QPushButton#primary { background: #2f6fde; color: white; border: none; border-radius: 4px; font-weight: 600; }
QPushButton#primary:disabled { background: #a9bde3; }
QProgressBar { height: 10px; border: none; background: #e6e9ee; border-radius: 5px; }
QProgressBar::chunk { background: #2f6fde; border-radius: 5px; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        from whosaid.gui.meeting_tab import MeetingTab
        from whosaid.gui.people_tab import PeopleTab
        from whosaid.gui.settings_tab import SettingsTab

        self.setWindowTitle(f"{APP_NAME} — 누가 말했나  v{__version__}")
        self.resize(1100, 780)
        self.busy = False
        self.engine = Engine()

        self.tabs = QTabWidget()
        self.people_tab = PeopleTab(self)
        self.meeting_tab = MeetingTab(self)
        self.settings_tab = SettingsTab(self)
        self.tabs.addTab(self.meeting_tab, "회의록 만들기")
        self.tabs.addTab(self.people_tab, "참석자 목소리 등록")
        self.tabs.addTab(self.settings_tab, "설정")
        self.setCentralWidget(self.tabs)
        if not self.engine.store.people():
            self.tabs.setCurrentWidget(self.people_tab)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.tabs.tabBar().setEnabled(not busy)

    def apply_settings(self, settings) -> None:
        old = self.engine.settings
        self.engine.settings = settings
        if old.cpu_threads != settings.cpu_threads:
            self.engine._diarizer = None
        self.meeting_tab.refresh_settings()

    def closeEvent(self, e) -> None:
        if self.busy and QMessageBox.question(
            self, APP_NAME, "작업 중입니다. 정말 닫을까요?"
        ) != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        for tab in (self.meeting_tab, self.people_tab):
            if tab.task and tab.task.isRunning():
                tab.task.cancel()
                tab.task.wait(5000)
        e.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
