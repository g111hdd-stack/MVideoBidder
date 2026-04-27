from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from domain.dtos import Task, Campaign

logger = logging.getLogger("mvideo_bidder")


class BaseWorker(QObject):
    finished = Signal(list, dict)
    error = Signal(str)
    log = Signal(str)

    def __init__(self, webdrivers: list, user_state: dict | None = None, cycle_interval_ms: int = 0) -> None:
        super().__init__()
        self.webdrivers = webdrivers
        self.user_state = user_state or {}
        self.cycle_interval_ms = cycle_interval_ms
        self._stop_requested = False

    def request_stop(self) -> None:
        logger.info("Bidder остановлен.")
        self._stop_requested = True

    @staticmethod
    def campaigns_to_rows(self, campaigns: list[Campaign]) -> list[dict]:
        rows: list[dict] = []

        client_id = ""
        shop_name = ""

        if self.webdriver is not None:
            client_id = str(getattr(self.webdriver, "client_id", "") or "")
            shop_name = str(getattr(self.webdriver, "name_company", "") or "")

        for campaign in campaigns:
            for item in campaign.items:
                rows.append({
                    "client_id": client_id,
                    "shop": shop_name,

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

    @staticmethod
    def campaigns_to_rows_for_webdriver(webdriver, campaigns: list[Campaign]) -> list[dict]:
        rows: list[dict] = []

        client_id = str(getattr(webdriver, "client_id", "") or "")
        shop_name = str(getattr(webdriver, "name_company", "") or "")

        for campaign in campaigns:
            for item in campaign.items:
                rows.append({
                    "client_id": client_id,
                    "shop": shop_name,

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
            key = f'{row.get("client_id", "")}::{row["campaign_id"]}::{row["sku"]}'
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
                    client_id=str(row.get("client_id", "")),
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
            logger.info("Обновление данных из кабинетов...")

            all_rows = []

            for webdriver in self.webdrivers:
                if self._stop_requested:
                    logger.info("Обновление остановлено")
                    self.finished.emit([], self.user_state)
                    return

                shop_name = getattr(webdriver, "name_company", "")
                logger.info(f"Обновление магазина: {shop_name}")

                campaigns = webdriver.bidder_info()
                rows = self.campaigns_to_rows_for_webdriver(webdriver, campaigns)
                all_rows.extend(rows)

            rows_for_table = self.apply_user_state_to_rows(all_rows)

            self.finished.emit(rows_for_table, self.user_state)

        except Exception as e:
            self.error.emit(str(e))


class BidderCycleWorker(BaseWorker):
    def run(self) -> None:
        interval_minutes = self.cycle_interval_ms // 60000

        try:
            logger.info("Запуск цикла Bidder...")

            all_rows = []

            for webdriver in self.webdrivers:
                if self._stop_requested:
                    logger.info("Цикл остановлен")
                    self.finished.emit([], self.user_state)
                    return

                client_id = str(getattr(webdriver, "client_id", "") or "")
                shop_name = str(getattr(webdriver, "name_company", "") or "")

                logger.info(f"Обработка магазина: {shop_name} / client_id={client_id}")

                campaigns = webdriver.bidder_info()
                fresh_rows = self.campaigns_to_rows_for_webdriver(webdriver, campaigns)
                rows_for_shop = self.apply_user_state_to_rows(fresh_rows)

                tasks = self.build_tasks_from_rows(rows_for_shop)

                # На всякий случай оставляем только задачи текущего магазина
                tasks = [
                    task for task in tasks
                    if str(task.client_id) == client_id
                ]

                logger.info(f"{shop_name}: найдено задач: {len(tasks)}")

                if tasks and not self._stop_requested:
                    webdriver.bidder(tasks)

                all_rows.extend(rows_for_shop)

            logger.info(f"Цикл Bidder завершён. Следующий запуск через {interval_minutes} мин.")
            self.finished.emit(all_rows, self.user_state)

        except Exception as e:
            self.error.emit(str(e))
