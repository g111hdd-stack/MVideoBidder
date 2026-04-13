import sys

from PySide6.QtWidgets import QApplication

from gui_main import MainWindow
from log_window import LogWindow
from web_driver.wd import WebDriver
from database.db import DbConnection
from log.app_logger import setup_logger


def main() -> int:
    logger = setup_logger()
    logger.info("Запуск приложения")

    app = QApplication(sys.argv)

    db_conn = DbConnection()
    market = db_conn.get_market()
    url = market.marketplace_info.link

    logger.info("Данные маркетплейса получены")

    webdriver = WebDriver(market, db_conn)
    logger.info("WebDriver создан")

    window = MainWindow(
        db_conn=db_conn,
        webdriver=webdriver,
        url=url,
        auto_load=False,
    )

    log_window = LogWindow(
        main_window=window,
        webdriver=webdriver,
        url=url,
    )

    def on_app_quit() -> None:
        try:
            logger.info("Завершение приложения")
            webdriver.quit()
            logger.info("WebDriver закрыт")
        except Exception as e:
            logger.exception(f"Ошибка при закрытии WebDriver: {e}")

    app.aboutToQuit.connect(on_app_quit)

    log_window.show()
    logger.info("Окно логов показано")

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
