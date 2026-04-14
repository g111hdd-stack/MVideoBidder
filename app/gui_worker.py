from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from domain.dtos import Task, Campaign

logger = logging.getLogger("mvideo_bidder")


class BaseWorker(QObject):
    finished = Signal(list, dict)
    error = Signal(str)
    log = Signal(str)

    def __init__(self, webdriver, user_state: dict | None = None) -> None:
        super().__init__()
        self.webdriver = webdriver
        self.user_state = user_state or {}
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    @staticmethod
    def campaigns_to_rows(campaigns: list[Campaign]) -> list[dict]:
        rows: list[dict] = []

        for campaign in campaigns:
            for item in campaign.items:
                rows.append({
                    "campaign_id": int(campaign.campaign_id),
                    "campaign_name": str(campaign.name),
                    "campaign_type": str(campaign.campaign_type),
                    "payment_model": str(campaign.payment_model),
                    "budget_total": int(campaign.budget_total),
                    "from_date": campaign.from_date.isoformat(),
                    "regions": list(campaign.regions),
                    "status": str(campaign.status),
                    "spent_daily": int(campaign.spent_daily),
                    "spent_total": int(campaign.spent_total),
                    "shows": int(campaign.shows),
                    "clicks": int(campaign.clicks),
                    "created_at": campaign.created_at.isoformat(),
                    "updated_at": campaign.updated_at.isoformat(),

                    "sku": int(item.sku),
                    "item_name": str(item.name),
                    "category": str(item.category or ""),
                    "category_id": int(item.category_id),
                    "keywords": list(item.keywords),
                    "quantity": int(item.quantity),
                    "bid": float(item.bid),
                    "limit": 0.0,
                    "position": 0,
                })

        return rows

    def apply_user_state_to_rows(self, rows: list[dict]) -> list[dict]:
        for row in rows:
            key = f'{row["campaign_id"]}::{row["sku"]}'
            values = self.user_state.get(key)

            if not values:
                continue

            row["limit"] = float(values.get("limit", row.get("limit", 0.0)))
            row["position"] = int(values.get("position", row.get("position", 0)))

        return rows

    def build_tasks_from_rows(self, rows: list[dict]) -> list[Task]:
        tasks: list[Task] = []

        for row in rows:
            key = f'{row["campaign_id"]}::{row["sku"]}'
            values = self.user_state.get(key, {})

            limit = float(values.get("limit", row.get("limit", 0.0)))
            position = int(values.get("position", row.get("position", 0)))
            quantity = int(row.get("quantity", 0))

            if not all([limit, position, quantity]):
                continue

            tasks.append(
                Task(
                    campaign_id=int(row["campaign_id"]),
                    sku=int(row["sku"]),
                    category_id=int(row.get("category_id", 0)),
                    region=list(row.get("regions", [])),
                    keywords=list(row.get("keywords", [])),
                    bid=float(row.get("bid", 0.0)),
                    limit=limit,
                    position=position,
                )
            )

        return tasks


class RefreshWorker(BaseWorker):
    def run(self) -> None:
        try:
            logger.info("Обновление данных из кабинета...")
            self.log.emit("Обновление данных из кабинета...")
            campaigns = self.webdriver.bidder_info()

            if self._stop_requested:
                logger.info("Обновление данных из кабинета...")
                self.log.emit("Обновление остановлено")
                self.finished.emit([], self.user_state)
                return

            fresh_rows = self.campaigns_to_rows(campaigns)
            rows_for_table = self.apply_user_state_to_rows(fresh_rows)

            self.finished.emit(rows_for_table, self.user_state)

        except Exception as e:
            self.error.emit(str(e))


class BidderCycleWorker(BaseWorker):
    def run(self) -> None:
        try:
            logger.info("Запуск цикла bidder...")
            self.log.emit("Запуск цикла bidder...")
            campaigns = self.webdriver.bidder_info()

            if self._stop_requested:
                logger.info("Цикл остановлен")
                self.log.emit("Цикл остановлен")
                self.finished.emit([], self.user_state)
                return

            fresh_rows = self.campaigns_to_rows(campaigns)
            rows_for_table = self.apply_user_state_to_rows(fresh_rows)
            tasks = self.build_tasks_from_rows(rows_for_table)

            logger.info(f"Найдено задач: {len(tasks)}")
            self.log.emit(f"Найдено задач: {len(tasks)}")

            if tasks and not self._stop_requested:
                self.webdriver.bidder(tasks)

            self.finished.emit(rows_for_table, self.user_state)

        except Exception as e:
            self.error.emit(str(e))
