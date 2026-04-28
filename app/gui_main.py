import re
import json
import logging

from updater.version import APP_VERSION

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget, QDialogButtonBox, QDialog, QLabel, QSpinBox, QDockWidget, QTextEdit, \
    QFrame, QLineEdit, QMenu
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QHeaderView, QMainWindow, QMessageBox, QPushButton, QTableView

from domain.dtos import Task
from utils.app_logger import set_gui_logger_callback
from app.gui_worker import RefreshWorker, BidderCycleWorker

TABLE_HEADERS = [
    "Магазин",
    "Рекламное ID",
    "Название РК",
    "Статус РК",
    "SKU",
    "Название товара",
    "Категория товара",
    "Остаток",
    "Ставка",
    "Лимит ставки",
    "Позиция",
]
SHOP_COLUMN = 0
ID_COLUMN = 1
CAMPAIGN_NAME_COLUMN = 2
STATUS_COLUMN = 3
SKU_COLUMN = 4
ITEM_NAME_COLUMN = 5
CATEGORY_COLUMN = 6
QUANTITY_COLUMN = 7
BID_COLUMN = 8
LIMIT_COLUMN = 9
POSITION_COLUMN = 10

logger = logging.getLogger("mvideo_bidder")


class CampaignTableModel(QAbstractTableModel):
    def __init__(self, rows: list[dict] | None = None, on_change=None) -> None:
        super().__init__()
        self._rows = rows or []
        self._on_change = on_change

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(TABLE_HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return TABLE_HEADERS[section]
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = self._rows[index.row()]

        column_map = {
            SHOP_COLUMN: "shop",
            ID_COLUMN: "campaign_id",
            CAMPAIGN_NAME_COLUMN: "campaign_name",
            STATUS_COLUMN: "status",
            SKU_COLUMN: "sku",
            ITEM_NAME_COLUMN: "item_name",
            CATEGORY_COLUMN: "category",
            QUANTITY_COLUMN: "quantity",
            BID_COLUMN: "bid",
            LIMIT_COLUMN: "limit",
            POSITION_COLUMN: "position",
        }

        key = column_map.get(index.column())
        value = row.get(key, "")

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == POSITION_COLUMN:
                return ""
            return str(value)

        if role == Qt.ItemDataRole.EditRole:
            return value

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter

        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = Qt.ItemFlag.ItemIsSelectable
        flags |=  Qt.ItemFlag.ItemIsEnabled
        if index.column() in (LIMIT_COLUMN, POSITION_COLUMN):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = self._rows[index.row()]

        if index.column() == LIMIT_COLUMN:
            row["limit"] = float(value) if str(value).strip() else 0.0
        elif index.column() == POSITION_COLUMN:
            row["position"] = int(value) if str(value).strip() else 0
        else:
            return False

        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])

        if self._on_change is not None:
            self._on_change()

        return True

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_rows(self) -> list[dict]:
        return self._rows

class CycleIntervalDialog(QDialog):
    def __init__(self, current_minutes: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Интервал между циклами")
        self.setModal(True)
        self.resize(300, 120)

        layout = QVBoxLayout(self)

        info_label = QLabel("Укажите интервал между циклами в минутах:")
        layout.addWidget(info_label)

        self.spin_box = QSpinBox()
        self.spin_box.setMinimum(2)
        self.spin_box.setMaximum(1440)
        self.spin_box.setValue(max(2, current_minutes))
        self.spin_box.setSuffix(" мин")
        layout.addWidget(self.spin_box)

        self.note_label = QLabel("Минимальное значение: 2 минуты")
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox()
        std = QDialogButtonBox.StandardButton.Ok
        std |= QDialogButtonBox.StandardButton.Cancel
        buttons.setStandardButtons(std)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_minutes(self) -> int:
        return int(self.spin_box.value())

class CheckableFilterMenu(QMenu):
    def mouseReleaseEvent(self, event) -> None:
        action = self.actionAt(event.pos())

        if action is not None and action.isCheckable():
            action.trigger()
            event.accept()
            return

        super().mouseReleaseEvent(event)

class MainWindow(QMainWindow):
    gui_log_signal = Signal(str)

    def __init__(self, db_conn, webdrivers: list | None = None, url: str = "", auto_load: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(f"MVideo Bidder v{APP_VERSION}")
        self.resize(1450, 700)

        self.db_conn = db_conn
        self.webdrivers = webdrivers or []
        self.url = url
        self.auto_load = auto_load
        self.storage_path = Path("campaign_state.json")
        self.settings_path = Path("app_settings.json")

        self.is_running = False
        self.cycle_interval_ms = 2 * 60 * 1000
        self.bidder_timer = QTimer(self)
        self.bidder_timer.setSingleShot(True)
        self.bidder_timer.timeout.connect(self.run_bidder_cycle)

        self.worker_thread = None
        self.worker = None
        self.worker_busy = False

        self.model = CampaignTableModel(on_change=self.save_table_state)

        self.filters_expanded = True

        self.filter_menus = {}
        self.filter_actions = {
            "shop": {},
            "campaign_id": {},
            "category": {},
        }

        self._init_ui()
        self._load_app_settings()
        self._init_log_dock()
        self.gui_log_signal.connect(self.append_log)
        set_gui_logger_callback(self.gui_log_signal.emit)
        self._load_empty_rows()
        if self.auto_load:
            QTimer.singleShot(0, self.load_campaigns)

    def _init_ui(self) -> None:
        root = QWidget()
        main_layout = QVBoxLayout(root)

        button_layout = QHBoxLayout()

        self.run_button = QPushButton("Запустить")
        self.refresh_button = QPushButton("Обновить")
        self.logs_button = QPushButton("Показать логи")
        self.interval_button = QPushButton("Интервал: 2 мин")
        self.status_label = QLabel("Цикл остановлен")

        self.run_button.clicked.connect(self.toggle_bidder)
        self.refresh_button.clicked.connect(self.refresh_from_cabinet)
        self.logs_button.clicked.connect(self.toggle_logs)
        self.interval_button.clicked.connect(self.open_interval_dialog)

        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.logs_button)
        button_layout.addWidget(self.interval_button)
        button_layout.addWidget(self.status_label)
        button_layout.addStretch()

        self.filter_bar = QFrame()
        self.filter_bar.setFrameShape(QFrame.Shape.StyledPanel)

        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setContentsMargins(6, 6, 6, 6)

        self.filters_toggle_button = QPushButton("☰")
        self.filters_toggle_button.setFixedWidth(42)
        self.filters_toggle_button.setToolTip("Показать / скрыть фильтры")
        self.filters_toggle_button.clicked.connect(self.toggle_filters_panel)

        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("Поиск по магазину, ID, категории, SKU")
        self.search_filter.textChanged.connect(self.apply_filters)

        self.shop_filter_button = QPushButton("Магазины")
        self.campaign_filter_button = QPushButton("Рекламное ID")
        self.category_filter_button = QPushButton("Категории")

        self.shop_filter_menu = CheckableFilterMenu(self)
        self.campaign_filter_menu = CheckableFilterMenu(self)
        self.category_filter_menu = CheckableFilterMenu(self)

        self.shop_filter_button.setMenu(self.shop_filter_menu)
        self.campaign_filter_button.setMenu(self.campaign_filter_menu)
        self.category_filter_button.setMenu(self.category_filter_menu)

        self.filter_menus = {
            "shop": self.shop_filter_menu,
            "campaign_id": self.campaign_filter_menu,
            "category": self.category_filter_menu,
        }

        filter_layout.addWidget(self.filters_toggle_button)
        filter_layout.addWidget(self.search_filter)
        filter_layout.addWidget(self.shop_filter_button)
        filter_layout.addWidget(self.campaign_filter_button)
        filter_layout.addWidget(self.category_filter_button)
        filter_layout.addStretch()

        self.table = QTableView()
        self.table.setModel(self.model)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)

        self.table.setStyleSheet("""
            QTableView::item:hover {
                background-color: rgba(110, 110, 110, 120);
            }
            QTableView::item:selected {
                background-color: rgba(110, 110, 110, 170);
                color: white;
            }
        """)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        header.setSectionResizeMode(ID_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(CAMPAIGN_NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(STATUS_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(SKU_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(ITEM_NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(CATEGORY_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(QUANTITY_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(BID_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(LIMIT_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(POSITION_COLUMN, QHeaderView.ResizeMode.Fixed)

        header.setMinimumSectionSize(90)

        self.table.setColumnWidth(ID_COLUMN, 90)
        self.table.setColumnWidth(SKU_COLUMN, 90)
        self.table.setColumnWidth(QUANTITY_COLUMN, 90)
        self.table.setColumnWidth(BID_COLUMN, 90)
        self.table.setColumnWidth(LIMIT_COLUMN, 90)
        self.table.setColumnWidth(POSITION_COLUMN, 90)

        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.filter_bar)
        main_layout.addWidget(self.table)

        self.setCentralWidget(root)

    def toggle_filters_panel(self) -> None:
        self.filters_expanded = not self.filters_expanded

        self.search_filter.setVisible(self.filters_expanded)
        self.shop_filter_button.setVisible(self.filters_expanded)
        self.campaign_filter_button.setVisible(self.filters_expanded)
        self.category_filter_button.setVisible(self.filters_expanded)

        self.filters_toggle_button.setText("☰" if self.filters_expanded else "▶")

    def rebuild_filter_menus(self) -> None:
        rows = self.model.get_rows()

        shops = sorted({
            str(row.get("shop", ""))
            for row in rows
            if str(row.get("shop", "")).strip()
        })

        campaign_ids = sorted({
            str(row.get("campaign_id", ""))
            for row in rows
            if str(row.get("campaign_id", "")).strip()
               and str(row.get("campaign_id", "")) != "0"
        })

        categories = sorted({
            str(row.get("category", ""))
            for row in rows
            if str(row.get("category", "")).strip()
        })

        self.rebuild_one_filter_menu("shop", shops)
        self.rebuild_one_filter_menu("campaign_id", campaign_ids)
        self.rebuild_one_filter_menu("category", categories)

    def rebuild_one_filter_menu(self, filter_name: str, values: list[str]) -> None:
        menu = self.filter_menus[filter_name]

        old_selected = self.get_selected_filter_values(filter_name)

        if not old_selected:
            old_selected = set(values)

        menu.clear()
        self.filter_actions[filter_name] = {}

        all_action = QAction("Все", self)
        all_action.setCheckable(True)
        all_action.setChecked(len(old_selected) == len(values))
        all_action.triggered.connect(
            lambda checked, name=filter_name: self.set_all_filter_values(name, checked)
        )

        menu.addAction(all_action)
        self.filter_actions[filter_name]["__all__"] = all_action

        menu.addSeparator()

        for value in values:
            action = QAction(value, self)
            action.setCheckable(True)
            action.setChecked(value in old_selected)
            action.triggered.connect(
                lambda _checked, name=filter_name: self.on_filter_action_changed(name)
            )

            menu.addAction(action)
            self.filter_actions[filter_name][value] = action

    def set_all_filter_values(self, filter_name: str, checked: bool) -> None:
        actions = self.filter_actions.get(filter_name, {})

        for value, action in actions.items():
            if value == "__all__":
                continue

            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)

        self.apply_filters()

    def on_filter_action_changed(self, filter_name: str) -> None:
        actions = self.filter_actions.get(filter_name, {})

        real_actions = [
            action
            for value, action in actions.items()
            if value != "__all__"
        ]

        all_checked = bool(real_actions) and all(action.isChecked() for action in real_actions)

        all_action = actions.get("__all__")
        if all_action is not None:
            all_action.blockSignals(True)
            all_action.setChecked(all_checked)
            all_action.blockSignals(False)

        self.apply_filters()

    def get_selected_filter_values(self, filter_name: str) -> set[str]:
        result = set()

        for value, action in self.filter_actions.get(filter_name, {}).items():
            if value == "__all__":
                continue

            if action.isChecked():
                result.add(value)

        return result

    def filter_has_values(self, filter_name: str) -> bool:
        return any(
            value != "__all__"
            for value in self.filter_actions.get(filter_name, {})
        )

    def apply_filters(self) -> None:
        search_text = self.search_filter.text().strip().lower()

        selected_shops = self.get_selected_filter_values("shop")
        selected_campaign_ids = self.get_selected_filter_values("campaign_id")
        selected_categories = self.get_selected_filter_values("category")

        has_shop_filter = self.filter_has_values("shop")
        has_campaign_filter = self.filter_has_values("campaign_id")
        has_category_filter = self.filter_has_values("category")

        for row_index, row in enumerate(self.model.get_rows()):
            row_shop = str(row.get("shop", ""))
            row_client_id = str(row.get("client_id", ""))
            row_campaign_id = str(row.get("campaign_id", ""))
            row_campaign_name = str(row.get("campaign_name", ""))
            row_sku = str(row.get("sku", ""))
            row_item_name = str(row.get("item_name", ""))
            row_category = str(row.get("category", ""))

            visible = True

            if has_shop_filter and row_shop not in selected_shops:
                visible = False

            if has_campaign_filter and row_campaign_id not in selected_campaign_ids:
                visible = False

            if has_category_filter and row_category not in selected_categories:
                visible = False

            if search_text:
                search_area = " ".join([
                    row_shop,
                    row_client_id,
                    row_campaign_id,
                    row_campaign_name,
                    row_sku,
                    row_item_name,
                    row_category,
                ]).lower()

                if search_text not in search_area:
                    visible = False

            self.table.setRowHidden(row_index, not visible)

        self.fill_position_widgets()

    def sync_table_state(self) -> None:
        try:
            current_data = self.load_table_state()
            changed = False

            for row in self.model.get_rows():
                key = self._build_row_key(row)

                new_value = {
                    "campaign_id": int(row["campaign_id"]),
                    "sku": int(row["sku"]),
                    "category_id": int(row["category_id"]),
                    "region": list(row["region"]),
                    "keywords": list(row["keywords"]),
                    "quantity": list(row["quantity"]),
                    "bid": float(row["bid"]),
                    "limit": float(row["limit"]),
                    "position": int(row["position"]),
                }

                old_value = current_data.get(key)

                if old_value != new_value:
                    current_data[key] = new_value
                    changed = True

            if changed:
                self.storage_path.write_text(
                    json.dumps(current_data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )

        except Exception as e:
            logger.exception(f"Ошибка синхронизации состояния таблицы: {e}")



    def _load_empty_rows(self) -> None:
        rows = []
        for _ in range(10):
            rows.append({
                "client_id": "",
                "shop": "",
                "campaign_id": 0,
                "campaign_name": "",
                "status": "",
                "sku": 0,
                "item_name": "",
                "category": "",
                "category_id": 0,
                "region": [],
                "regions": [],
                "keywords": [],
                "quantity": 0,
                "bid": 0.0,
                "limit": 0.0,
                "position": 0,
            })

        rows = self.apply_saved_state(rows)
        self.model.set_rows(rows)
        self.rebuild_filter_menus()
        self.apply_filters()

    def _clear_position_widgets(self) -> None:
        for row in range(self.model.rowCount()):
            index = self.model.index(row, POSITION_COLUMN)
            widget = self.table.indexWidget(index)

            if widget is not None:
                self.table.setIndexWidget(index, None)
                widget.setParent(None)
                widget.deleteLater()

    def fill_position_widgets(self) -> None:
        self._clear_position_widgets()

        for row in range(self.model.rowCount()):
            if self.table.isRowHidden(row):
                continue

            index = self.model.index(row, POSITION_COLUMN)

            combo = QComboBox(self.table)
            combo.addItems(["0", "1", "2", "3", "4"])
            combo.setMaxVisibleItems(5)
            combo.setCurrentText(str(self.model.data(index, Qt.ItemDataRole.EditRole) or "0"))
            combo.currentTextChanged.connect(
                lambda value, current_row=row: self._on_position_changed(current_row, value)
            )

            self.table.setIndexWidget(index, combo)

    def _on_position_changed(self, row: int, value: str) -> None:
        try:
            new_position = int(value)
        except ValueError:
            new_position = 0

        current_row = self.model.get_rows()[row]
        old_position = int(current_row.get("position", 0))

        if self._has_position_conflict(row, new_position):
            QMessageBox.warning(
                self,
                "Дублирующаяся позиция",
                (
                    f"Позиция {new_position} уже занята для этой РК и Категории.\n"
                    f"Позиции 1–4 должны быть уникальны в рамках РК и Категории"
                ),
            )

            index = self.model.index(row, POSITION_COLUMN)
            widget = self.table.indexWidget(index)
            if isinstance(widget, QComboBox):
                widget.blockSignals(True)
                widget.setCurrentText(str(old_position))
                widget.blockSignals(False)
            return

        index = self.model.index(row, POSITION_COLUMN)
        self.model.setData(index, value, Qt.ItemDataRole.EditRole)

    def _has_position_conflict(self, row: int, new_position: int) -> bool:
        if new_position == 0:
            return False

        current_row = self.model.get_rows()[row]
        client_id = str(current_row.get("client_id", ""))
        campaign_id = int(current_row.get("campaign_id", 0))
        category_id = int(current_row.get("category_id", 0))

        for i, other_row in enumerate(self.model.get_rows()):
            if i == row:
                continue

            if (
                    str(other_row.get("client_id", "")) == client_id
                    and int(other_row.get("campaign_id", 0)) == campaign_id
                    and int(other_row.get("category_id", 0)) == category_id
                    and int(other_row.get("position", 0)) == new_position
            ):
                return True

        return False

    def campaigns_to_rows(self, campaigns) -> list[dict]:
        if not self.webdrivers:
            return []

        return self.campaigns_to_rows_for_webdriver(self.webdrivers[0], campaigns)

    def campaigns_to_rows_for_webdriver(self, webdriver, campaigns) -> list[dict]:
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

        return self.apply_saved_state(rows)

    def load_campaigns(self) -> None:
        try:
            rows = []

            for webdriver in self.webdrivers:
                webdriver.load_url(self.url)
                campaigns = webdriver.bidder_info()

                rows.extend(
                    self.campaigns_to_rows_for_webdriver(webdriver, campaigns)
                )

            if not rows:
                QMessageBox.information(self, "Информация", "Кампании не найдены")
                return

            self.model.set_rows(rows)
            self.rebuild_filter_menus()
            self.apply_filters()
            self.save_table_state()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def save_table_state(self) -> None:
        self.save_json_state(self.model.get_rows(), self.collect_user_state())

    @staticmethod
    def _build_row_key(row: dict) -> str:
        return f'{row.get("client_id", "")}::{row["campaign_id"]}::{row["sku"]}'

    def build_tasks_from_json(self) -> list[Task]:
        tasks: list[Task] = []
        data = self.load_table_state()

        for campaign in data.values():
            campaign_id = int(campaign.get("campaign_id", 0))
            regions = list(campaign.get("regions", []))

            for item in campaign.get("items", []):
                limit = float(item.get("limit", 0.0))
                position = int(item.get("position", 0))
                quantity = int(item.get("quantity", 0))

                if not all([limit, position, quantity]):
                    continue

                tasks.append(
                    Task(
                        campaign_id=campaign_id,
                        sku=int(item.get("sku", 0)),
                        category_id=int(item.get("category_id", 0)),
                        region=regions,
                        keywords=list(item.get("keywords", [])),
                        bid=float(item.get("bid", 0.0)),
                        limit=limit,
                        position=position,
                    )
                )

        return tasks

    def collect_user_state(self) -> dict:
        user_state = {}

        for row in self.model.get_rows():
            key = self._build_row_key(row)
            user_state[key] = {
                "limit": float(row.get("limit", 0.0)),
                "position": int(row.get("position", 0)),
            }

        return user_state

    def save_json_state(self, rows: list[dict], user_state: dict | None = None) -> None:
        try:
            if user_state is None:
                user_state = {}

            data = {}

            for row in rows:
                campaign_key = f'{row.get("client_id", "")}::{int(row["campaign_id"])}'
                row_key = self._build_row_key(row)

                user_values = user_state.get(row_key, {})
                limit = float(user_values.get("limit", row.get("limit", 0.0)))
                position = int(user_values.get("position", row.get("position", 0)))

                data[campaign_key] = {
                        "client_id": str(row.get("client_id", "")),
                        "shop": str(row.get("shop", "")),
                        "campaign_id": int(row["campaign_id"]),
                        "name": str(row.get("campaign_name", "")),
                        "campaign_type": str(row.get("campaign_type", "")),
                        "payment_model": str(row.get("payment_model", "")),
                        "budget_total": int(row.get("budget_total", 0)),
                        "from_date": str(row.get("from_date", "")),
                        "regions": list(row.get("regions", row.get("region", []))),
                        "status": str(row.get("status", "")),
                        "spent_daily": int(row.get("spent_daily", 0)),
                        "spent_total": int(row.get("spent_total", 0)),
                        "shows": int(row.get("shows", 0)),
                        "clicks": int(row.get("clicks", 0)),
                        "created_at": str(row.get("created_at", "")),
                        "updated_at": str(row.get("updated_at", "")),
                        "items": [],
                    }

                data[campaign_key]["items"].append({
                    "sku": int(row["sku"]),
                    "name": str(row.get("item_name", "")),
                    "category": str(row.get("category", "")),
                    "category_id": int(row.get("category_id", 0)),
                    "keywords": list(row.get("keywords", [])),
                    "quantity": int(row.get("quantity", 0)),
                    "bid": float(row.get("bid", 0.0)),
                    "limit": limit,
                    "position": position,
                })

            text = json.dumps(data, ensure_ascii=False, indent=2)

            def compact_region(match: re.Match) -> str:
                prefix = match.group(1)
                body = match.group(2)
                numbers = [line.strip().rstrip(",") for line in body.splitlines() if line.strip()]
                return f'{prefix}[{", ".join(numbers)}]'

            text = re.sub(
                r'("regions": )\[\n(.*?)\n\s*]',
                compact_region,
                text,
                flags=re.DOTALL,
            )

            self.storage_path.write_text(text, encoding="utf-8")

        except Exception as e:
            logger.exception(f"Ошибка сохранения состояния json: {e}")

    def load_table_state(self) -> dict:
        try:
            if not self.storage_path.exists():
                return {}

            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.exception(f"Ошибка загрузки состояния таблицы: {e}")
            return {}

    def load_app_settings(self) -> dict:
        try:
            if not self.settings_path.exists():
                return {}

            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.exception(f"Ошибка загрузки настроек приложения: {e}")
            return {}

    def save_app_settings(self) -> None:
        try:
            data = {
                "cycle_interval_minutes": self.cycle_interval_ms // 60000,
            }
            self.settings_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.exception(f"Ошибка сохранения настроек приложения: {e}")

    def _load_app_settings(self) -> None:
        settings = self.load_app_settings()

        minutes = int(settings.get("cycle_interval_minutes", 2))
        minutes = max(2, minutes)

        self.cycle_interval_ms = minutes * 60 * 1000

        if hasattr(self, "interval_button"):
            self.interval_button.setText(f"Интервал: {minutes} мин")

    def apply_saved_state(self, rows: list[dict]) -> list[dict]:
        saved_state = self.load_table_state()

        for row in rows:
            campaign_key = f'{row.get("client_id", "")}::{int(row["campaign_id"])}'
            saved_campaign = saved_state.get(campaign_key)

            if not saved_campaign:
                continue

            for saved_item in saved_campaign.get("items", []):
                if int(saved_item.get("sku", 0)) == int(row["sku"]):
                    row["limit"] = float(saved_item.get("limit", row["limit"]))
                    row["position"] = int(saved_item.get("position", row["position"]))
                    break

        return rows

    def start_bidder(self) -> None:
        if self.is_running:
            return

        self.is_running = True
        self.run_button.setText("Остановить")
        self.status_label.setText("Цикл запущен")
        self.run_bidder_cycle()

    def stop_bidder(self) -> None:
        self.is_running = False
        self.bidder_timer.stop()
        self.run_button.setText("Запустить")
        self.status_label.setText("Цикл остановлен")

        if self.worker is not None:
            self.worker.request_stop()
        else:
            logger.info("Bidder остановлен.")

    def toggle_bidder(self) -> None:
        if self.is_running:
            self.stop_bidder()
        else:
            self.start_bidder()

    def refresh_from_cabinet(self) -> None:
        self._start_worker(RefreshWorker)

    def run_bidder_cycle(self) -> None:
        if not self.is_running:
            return

        if self.worker_busy:
            logger.info("Предыдущий цикл ещё не завершён")
            return

        self._start_worker(BidderCycleWorker)

    def apply_user_state_to_rows(self, rows: list[dict], user_state: dict) -> list[dict]:
        for row in rows:
            key = self._build_row_key(row)
            values = user_state.get(key)

            if not values:
                continue

            row["limit"] = float(values.get("limit", row.get("limit", 0.0)))
            row["position"] = int(values.get("position", row.get("position", 0)))

        return rows

    def open_interval_dialog(self) -> None:
        current_minutes = max(2, self.cycle_interval_ms // 60000)
        dialog = CycleIntervalDialog(current_minutes=current_minutes, parent=self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        minutes = dialog.get_minutes()
        self.set_cycle_interval(minutes)

    def set_cycle_interval(self, minutes: int) -> None:
        minutes = max(2, int(minutes))
        self.cycle_interval_ms = minutes * 60 * 1000
        self.interval_button.setText(f"Интервал: {minutes} мин")

        self.save_app_settings()

        if self.is_running:
            QMessageBox.information(
                self,
                "Интервал обновлён",
                f"Новый интервал: {minutes} мин.\n"
                f"Он будет применён после текущего цикла или текущего ожидания."
            )
        else:
            QMessageBox.information(
                self,
                "Интервал обновлён",
                f"Новый интервал между циклами: {minutes} мин."
            )

    def _init_log_dock(self) -> None:
        self.log_dock = QDockWidget("Логи", self)
        self.log_dock.setObjectName("log_dock")
        dock = Qt.DockWidgetArea.RightDockWidgetArea
        dock |= Qt.DockWidgetArea.BottomDockWidgetArea
        self.log_dock.setAllowedAreas(dock)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        self.log_dock.setWidget(self.log_output)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

    def toggle_logs(self) -> None:
        visible = self.log_dock.isVisible()
        self.log_dock.setVisible(not visible)
        self.logs_button.setText("Скрыть логи" if not visible else "Показать логи")

    def append_log(self, text: str) -> None:
        if not hasattr(self, "log_output"):
            return

        self.log_output.append(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:
        set_gui_logger_callback(None)

        self.is_running = False
        self.bidder_timer.stop()

        if self.worker is not None:
            self.worker.request_stop()

        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(3000)

        super().closeEvent(event)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.worker_busy = busy
        self.refresh_button.setEnabled(not busy)

        if busy:
            self.status_label.setText(text or "Выполняется операция...")
        else:
            self.status_label.setText("Цикл запущен" if self.is_running else "Цикл остановлен")

    def _start_worker(self, worker_cls) -> None:
        if self.worker_busy:
            return

        if self.worker_thread is not None:
            return

        user_state = self.collect_user_state()

        self.worker_thread = QThread(self)
        self.worker = worker_cls(
            webdrivers=self.webdrivers,
            user_state=user_state,
            cycle_interval_ms=self.cycle_interval_ms
        )

        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.log.connect(self.append_log)

        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)

        self.worker_thread.finished.connect(self._cleanup_worker)

        self._set_busy(True, "Выполняется операция...")
        self.worker_thread.start()

    def _on_worker_finished(self, rows: list[dict], user_state: dict) -> None:
        if rows:
            self.save_json_state(rows, user_state)
            self.model.set_rows(rows)
            self.rebuild_filter_menus()
            self.apply_filters()

    def _on_worker_error(self, text: str) -> None:
        logger.exception(f"Ошибка worker: {text}")
        QMessageBox.critical(self, "Ошибка", text)

    def _cleanup_worker(self) -> None:
        self._set_busy(False)

        old_worker = self.worker
        old_thread = self.worker_thread

        self.worker = None
        self.worker_thread = None

        if old_worker is not None:
            old_worker.deleteLater()

        if old_thread is not None:
            old_thread.deleteLater()

        if self.is_running:
            self.bidder_timer.start(self.cycle_interval_ms)
            minutes = self.cycle_interval_ms // 60000
            self.status_label.setText(f"Ожидание следующего цикла: {minutes} мин")
