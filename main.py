import sys

from updater.update_service import check_update, run_update
from updater.update_dialogs import ask_update, show_update_window

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
        self.webdrivers = []
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
    def on_finished(self, db_conn, webdrivers, url: str) -> None:
        self.logger.info("Инициализация завершена")

        self.db_conn = db_conn
        self.webdrivers = webdrivers
        self.url = url

        self.window = MainWindow(
            db_conn=self.db_conn,
            webdrivers=self.webdrivers,
            url=self.url,
            auto_load=False,
        )

        self.log_window = LogWindow(
            main_window=self.window,
            webdrivers=self.webdrivers,
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
            for webdriver in self.webdrivers:
                try:
                    webdriver.quit()
                    self.logger.info(
                        f"WebDriver закрыт: {getattr(webdriver, 'name_company', '')}"
                    )
                except Exception as e:
                    self.logger.exception(f"Ошибка закрытия WebDriver: {e}")
        except Exception as e:
            self.logger.exception(f"Ошибка при закрытии WebDriver: {e}")


def main() -> int:
    logger = setup_logger()
    logger.info("Запуск приложения")

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(ICON_PATH))

    try:
        has_update, message, info = check_update()
        logger.info(f"Результат check_update: has_update={has_update}, message={message}")

        if has_update:
            approved = ask_update(message)

            if approved:
                logger.info("Пользователь согласился на обновление")

                update_window = show_update_window(app)

                def progress_cb(value: int):
                    update_window.set_progress(value)
                    app.processEvents()

                def log_cb(text: str):
                    update_window.append_log(text)
                    app.processEvents()

                def status_cb(text: str):
                    update_window.set_status(text)
                    app.processEvents()

                try:
                    run_update(
                        info,
                        progress_callback=progress_cb,
                        log_callback=log_cb,
                        status_callback=status_cb,
                    )
                    return 0
                except Exception as e:
                    update_window.close()
                    logger.exception(f"Ошибка запуска обновления: {e}")

                    QMessageBox.critical(
                        None,
                        "Ошибка обновления",
                        f"Не удалось скачать или запустить обновление.\n\n{e}"
                    )
            else:
                logger.info("Пользователь отказался от обновления")

    except Exception as e:
        logger.exception(f"Ошибка проверки обновления: {e}")

    controller = StartupController(app, logger)
    controller.start()

    app._startup_controller = controller
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
