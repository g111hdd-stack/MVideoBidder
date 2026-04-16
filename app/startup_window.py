from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QProgressBar, QVBoxLayout, QWidget


class StartupWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MVideo Bidder")
        self.setFixedSize(420, 140)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)

        root = QWidget()
        layout = QVBoxLayout(root)

        self.title_label = QLabel("Запуск приложения...")
        self.status_label = QLabel("Подготовка")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)

        self.setCentralWidget(root)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
