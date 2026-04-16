import sys

from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QApplication, QMessageBox

from config import ICON_PATH
from app.gui_main import MainWindow
from app.log_window import LogWindow
from utils.app_logger import setup_logger
from app.startup_window import StartupWindow
from app.startup_worker import StartupWorker


class StartupController(QObject):
    def __init__(self, app: QApplication, logger) -> None:
        super().__init__()
        self.app = app
        self.logger = logger

        self.startup_window = StartupWindow()
        self.startup_thread = QThread()
        self.startup_worker = StartupWorker()

        self.db_conn = None
        self.webdriver = None
        self.url = ""
        self.window = None
        self.log_window = None

        self.startup_worker.moveToThread(self.startup_thread)

        self.startup_thread.started.connect(self.startup_worker.run)
        self.startup_worker.progress.connect(self.on_progress)
        self.startup_worker.finished.connect(self.on_finished)
        self.startup_worker.error.connect(self.on_error)

        self.startup_worker.finished.connect(self.startup_thread.quit)
        self.startup_worker.error.connect(self.startup_thread.quit)

        self.startup_thread.finished.connect(self.startup_worker.deleteLater)
        self.startup_thread.finished.connect(self.startup_thread.deleteLater)

    def start(self) -> None:
        self.startup_window.show()
        self.startup_thread.start()

    @Slot(str)
    def on_progress(self, text: str) -> None:
        self.startup_window.set_status(text)
        self.logger.info(text)

    @Slot(object, object, str)
    def on_finished(self, db_conn, webdriver, url: str) -> None:
        self.logger.info("Инициализация завершена")

        self.db_conn = db_conn
        self.webdriver = webdriver
        self.url = url

        self.window = MainWindow(
            db_conn=self.db_conn,
            webdriver=self.webdriver,
            url=self.url,
            auto_load=False,
        )

        self.log_window = LogWindow(
            main_window=self.window,
            webdriver=self.webdriver,
            url=self.url,
        )

        self.app.aboutToQuit.connect(self.on_app_quit)

        self.startup_window.close()
        self.log_window.show()
        self.logger.info("Окно логов показано")

    @Slot(str)
    def on_error(self, text: str) -> None:
        self.logger.exception(f"Ошибка запуска: {text}")
        self.startup_window.close()
        QMessageBox.critical(None, "Ошибка запуска", text)
        self.app.quit()

    @Slot()
    def on_app_quit(self) -> None:
        try:
            self.logger.info("Завершение приложения")
            if self.webdriver is not None:
                self.webdriver.quit()
                self.logger.info("WebDriver закрыт")
        except Exception as e:
            self.logger.exception(f"Ошибка при закрытии WebDriver: {e}")


def main() -> int:
    logger = setup_logger()
    logger.info("Запуск приложения")

    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(ICON_PATH))

    controller = StartupController(app, logger)
    controller.start()

    app._startup_controller = controller

    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
