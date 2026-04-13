from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogWorker(QObject):
    log_message = Signal(str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, webdriver, url: str) -> None:
        super().__init__()
        self.webdriver = webdriver
        self.url = url

    def run(self) -> None:
        try:
            self.webdriver.set_gui_logger(self.log_message.emit)

            self.log_message.emit("Запуск загрузки данных...")
            campaigns = self._load_campaigns()
            self.log_message.emit("Данные успешно загружены. Открываем таблицу...")

            self.finished.emit(campaigns)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.webdriver.set_gui_logger(None)

    def _load_campaigns(self):
        self.webdriver.load_url(self.url)
        return self.webdriver.bidder_info()


class LogWindow(QMainWindow):
    def __init__(self, main_window, webdriver, url: str) -> None:
        super().__init__()
        self.setWindowTitle("MVideo Bidder - Логи запуска")
        self.resize(500, 200)

        self.main_window = main_window
        self.webdriver = webdriver
        self.url = url

        self.thread: QThread | None = None
        self.worker: LogWorker | None = None

        self._init_ui()
        QTimer.singleShot(0, self.start_loading)

    def _init_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        self.title_label = QLabel("Статус запуска:")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.log_output)

        self.setCentralWidget(root)

    def append_log(self, text: str) -> None:
        self.log_output.append(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def start_loading(self) -> None:
        self.thread = QThread(self)
        self.worker = LogWorker(self.webdriver, self.url)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_finished(self, campaigns) -> None:
        rows = self.main_window.campaigns_to_rows(campaigns)
        self.main_window.model.set_rows(rows)
        self.main_window._fill_position_widgets()
        self.main_window.save_table_state()

        self.main_window.show()
        self.close()

    def on_error(self, text: str) -> None:
        self.append_log(f"Ошибка: {text}")
