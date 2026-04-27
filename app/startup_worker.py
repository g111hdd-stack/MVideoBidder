from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from web_driver.wd import WebDriver
from database.db import DbConnection


class StartupWorker(QObject):
    progress = Signal(str)
    finished = Signal(object, object, str)
    error = Signal(str)

    def run(self) -> None:
        webdrivers = []

        try:
            self.progress.emit("Подключение к базе данных...")
            db_conn = DbConnection()

            self.progress.emit("Получение списка магазинов...")
            markets = db_conn.get_markets()

            if not markets:
                raise Exception("В базе не найдено ни одного магазина")

            url = markets[0].marketplace_info.link

            for i, market in enumerate(markets, start=1):
                name = market.name_company
                client_id = market.client_id

                self.progress.emit(
                    f"Запуск WebDriver {i}/{len(markets)}: {name} / client_id={client_id}"
                )

                webdriver = WebDriver(market, db_conn)
                webdrivers.append(webdriver)

            self.finished.emit(db_conn, webdrivers, url)

        except Exception as e:
            for webdriver in webdrivers:
                try:
                    webdriver.quit()
                except Exception:
                    pass

            self.error.emit(str(e))
