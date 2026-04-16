from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from web_driver.wd import WebDriver
from database.db import DbConnection


class StartupWorker(QObject):
    progress = Signal(str)
    finished = Signal(object, object, str)
    error = Signal(str)

    def run(self) -> None:
        try:
            self.progress.emit("Подключение к базе данных...")
            db_conn = DbConnection()

            self.progress.emit("Получение данных маркетплейса...")
            market = db_conn.get_market()
            url = market.marketplace_info.link

            self.progress.emit("Запуск WebDriver...")
            webdriver = WebDriver(market, db_conn)

            self.finished.emit(db_conn, webdriver, url)

        except Exception as e:
            self.error.emit(str(e))
