import json
import os
import time
import platform
import requests
import datetime
import logging


from typing import Type

from selenium import webdriver
from contextlib import suppress

from sqlalchemy.exc import IntegrityError
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import NoSuchWindowException, TimeoutException
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from database.models import Market
from database.db import DbConnection
from domain.dtos import Campaign, Item, Task
from .create_extension_proxy import create_firefox_proxy_addon

TIME_AWAIT = 10
logger = logging.getLogger("mvideo_bidder")


def get_moscow_time(timeout: int = 60, log_api: bool = False) -> datetime.datetime:
    try:
        response = requests.get("https://yandex.com/time/sync.json?geo=213",
                                timeout=timeout, verify=False)
        response.raise_for_status()
        data = response.json()
        moscow_time = datetime.datetime.fromtimestamp((data.get('time') / 1000),
                                                      tz=datetime.timezone(datetime.timedelta(hours=3))).replace(
            tzinfo=None)
        return moscow_time
    except Exception as e:
        if not log_api:
            with suppress(Exception):
                print(f"Ошибка при получении времени: {e}")
        return datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)


class AuthException(Exception):

    def __init__(self, message: str = ''):
        self.message = message
        super().__init__(self.message)


class WebDriver:

    def __init__(self, market: Type[Market], db_conn: DbConnection) -> None:
        self.gui_logger = None
        self.user = 'MVideoBidder'
        self.base_url = 'https://sellers.mvideo.ru'
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"
        self.db_conn = db_conn
        self.client_id = market.client_id
        self.proxy = market.connect_info.proxy
        self.phone = market.connect_info.phone
        self.name_company = market.name_company
        self.marketplace = market.marketplace_info
        self.browser_id = f"{self.phone}_{self.marketplace.marketplace.lower()}"
        self.log_startswith = f"{self.marketplace.marketplace} - {market.name_company}: "

        self.profile_path = os.path.join(os.getcwd(), f"profile/{self.browser_id}")

        os.makedirs(self.profile_path, exist_ok=True)

        self.proxy_auth_path = os.path.join(os.getcwd(), f"proxy_auth")
        os.makedirs(self.proxy_auth_path, exist_ok=True)

        ext_path = create_firefox_proxy_addon(self.proxy_auth_path, self.proxy)

        bit = '64' if platform.machine().endswith('64') else ''

        self.options = Options()

        # self.options.add_argument("-headless")

        self.options.add_argument("-no-remote")
        self.options.add_argument("-profile")
        self.options.add_argument(self.profile_path)

        self.options.set_preference("general.useragent.override", self.user_agent)

        self.options.set_preference("dom.webdriver.enabled", False)
        self.options.set_preference("useAutomationExtension", False)
        self.options.set_preference("media.peerconnection.enabled", True)
        self.options.set_preference("privacy.trackingprotection.enabled", False)
        self.options.set_preference("intl.accept_languages", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
        self.options.set_preference("toolkit.telemetry.reportingpolicy.firstRun", False)
        self.options.set_preference("app.update.auto", False)
        self.options.set_preference("app.update.enabled", False)

        self.options.binary_location = str(os.path.join(os.getcwd(),
                                                        f"browser/FirefoxPortable/App/Firefox{bit}/firefox.exe"))

        self.service = Service(executable_path=str(os.path.join(os.getcwd(), f"browser/geckodriver{bit}.exe")))

        self.driver = webdriver.Firefox(service=self.service, options=self.options)
        self.driver.install_addon(ext_path, temporary=True)

        self.driver.maximize_window()

    def set_gui_logger(self, logger_callback=None) -> None:
        self.gui_logger = logger_callback

    def log(self, message: str) -> None:
        logger.info(message)
        if getattr(self, "gui_logger", None):
            self.gui_logger(message)

    def check_auth(self) -> None:
        try:
            WebDriverWait(self.driver, TIME_AWAIT * 4).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )

            last_url = None

            for _ in range(6):
                if last_url == self.driver.current_url:
                    break
                last_url = self.driver.current_url
                WebDriverWait(self.driver, TIME_AWAIT * 4).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                time.sleep(TIME_AWAIT)
            else:
                Exception("Превышено время загрузки страницы")

            if self.marketplace.link in last_url:
                self.log(f"{self.log_startswith}Автоматизация запущена")

                self.mvideo_auth(self.marketplace)

            if self.marketplace.domain in last_url:
                self.log(f"{self.log_startswith}Вход в ЛК выполнен")

        except (NoSuchWindowException, InvalidSessionIdException):
            self.quit('Окно браузера было преждевременно закрыто')
        except Exception as e:
            self.quit(str(e).splitlines()[0])

    def mvideo_auth(self, marketplace: Market) -> bool | None:

        def check_login() -> bool:
            if 'https://sellers.mvideo.ru/mpa' in self.driver.current_url:
                self.driver.get(f'{self.marketplace.domain}')
                return True
            return False

        def enter(tr):
            self.log(f"{self.log_startswith}Ожидание кода на номер {self.phone}")

            for _ in range(3):
                try:
                    self.db_conn.add_phone_message(user=self.user,
                                                   phone=self.phone,
                                                   marketplace=marketplace.marketplace,
                                                   time_request=tr)
                    break
                except IntegrityError:
                    time.sleep(TIME_AWAIT)
            else:
                raise Exception('Ошибка параллельных запросов')

            mes = self.db_conn.get_phone_message(user=self.user, phone=self.phone, marketplace=marketplace.marketplace)

            mes = ''.join(ch for ch in mes if ch.isdigit())

            self.log(f"{self.log_startswith}Код на номер {self.phone} получен: {mes}")
            self.log(f"{self.log_startswith}Ввод кода {mes}")

            with suppress(TimeoutException):
                time.sleep(TIME_AWAIT)

                input_code = WebDriverWait(self.driver, TIME_AWAIT * 2).until(
                    expected_conditions.element_to_be_clickable(
                        (By.CSS_SELECTOR, "mpa-ui-input[formcontrolname='code'] input")))

                input_code.send_keys(mes)

                button_confirm = WebDriverWait(self.driver, TIME_AWAIT * 2).until(
                    expected_conditions.element_to_be_clickable(
                        (By.XPATH, "//button[contains(., 'Подтвердить')]")))

                self.log(f"{self.log_startswith} Нажимаем на кнопку подтвердить ")

                button_confirm.click()
                time.sleep(TIME_AWAIT)
                check_login()

                return
            raise Exception('Отсутствует поле ввода кода или кнопка подтверждения')

        for _ in range(3):
            try:
                time.sleep(TIME_AWAIT)
                self.log(f"{self.log_startswith}Ввод номера телефона {self.phone}")

                input_phone = WebDriverWait(self.driver, TIME_AWAIT * 4).until(
                    expected_conditions.element_to_be_clickable(
                        (By.CSS_SELECTOR, "input[name='phone']")))

                input_phone.clear()
                input_phone.send_keys(self.phone)

                self.log(f"{self.log_startswith}Нажимаем кнопку Войти")

                time_request = get_moscow_time()

                button_login = WebDriverWait(self.driver, TIME_AWAIT * 4).until(
                    expected_conditions.element_to_be_clickable(
                        (By.XPATH, "//button[contains(., 'Войти')]")))

                self.db_conn.check_phone_message(user=self.user, phone=self.phone, time_request=time_request)

                button_login.click()

                self.log(f"{self.log_startswith}Номер телефона введён, кнопка Войти нажата")

                enter(time_request)
                return

            except TimeoutException:
                self.log(f"{self.log_startswith}Не удалось найти поле телефона или кнопку Войти, повторная попытка")

        raise Exception('Страница не получена')

    def _dump_storage(self) -> dict:
        return self.driver.execute_script("""
            function readStorage(storage) {
                const result = {};
                for (let i = 0; i < storage.length; i++) {
                    const key = storage.key(i);
                    result[key] = storage.getItem(key);
                }
                return result;
            }

            return {
                local: readStorage(window.localStorage),
            };
        """)

    def _get_all_captured_requests(self) -> list[dict]:
        data = self.driver.execute_script("""
            return window.__mvideoCapturedRequests || [];
        """)
        return data or []

    def _build_requests_session(self) -> requests.Session:
        session = requests.Session()

        session.proxies = {
            "http": self.proxy,
            "https": self.proxy
        }

        for cookie in self.driver.get_cookies():
            session.cookies.set(
                name=cookie["name"],
                value=cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

        return session

    def _prepare_headers(self, authorization: str) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {authorization}"
        }

        return headers

    def capture_headers(self) -> dict[str, str]:
        data = self._dump_storage()
        kauth = data.get("local", {}).get("kauth")

        if not kauth:
            raise RuntimeError("Не удалось получить токен")

        authorization = json.loads(kauth).get("accessToken")

        if not authorization:
            raise RuntimeError("Не удалось получить токен")

        headers = self._prepare_headers(authorization)

        return headers

    def get_campaigns(self) -> list[dict]:
        for _ in range(3):
            try:
                headers = self.capture_headers()
                session = self._build_requests_session()

                response = session.get(
                    f"{self.base_url}/seller-api/v1/campaigns",
                    headers=headers,
                    timeout=30,
                )
                return response.json()
            except: # noqa
                continue
        return []

    def get_items(self, code: int) -> list[dict]:
        for _ in range(3):
            try:
                headers = self.capture_headers()
                session = self._build_requests_session()

                response = session.get(
                    f"{self.base_url}/seller-api/v1/campaigns/{code}/skus",
                    headers=headers,
                    timeout=30,
                )
                return response.json()
            except: # noqa
                continue
        return []

    def get_category(self, sku: int) -> dict:
        for _ in range(3):
            try:
                headers = self.capture_headers()
                session = self._build_requests_session()

                response = session.get(
                    f"{self.base_url}/seller-api/v1/categories",
                    params={"sku_ids": sku},
                    headers=headers,
                    timeout=30,
                )
                return response.json()
            except: # noqa
                continue
        return {}

    def get_top_bids(self, task: Task) -> list[int]:
        for _ in range(3):
            try:
                headers = self.capture_headers()
                session = self._build_requests_session()

                response = session.post(
                    f"{self.base_url}/seller-api/v1/topbids?limit=4",
                    json={
                        'category_id': task.category_id,
                        'queries': task.keywords,
                        'regions': task.region
                    },
                    headers=headers,
                    timeout=30,
                )
                return response.json()
            except: # noqa
                continue
        return []

    def change_bid(self, campaign_id: int, body: list[dict]) -> bool:
        for _ in range(3):
            try:
                headers = self.capture_headers()
                session = self._build_requests_session()

                response = session.post(
                    f"{self.base_url}/seller-api/v1/campaigns/{campaign_id}/skus",
                    json=body,
                    headers=headers,
                    timeout=30,
                )
                self.log(f"{self.log_startswith}Ответ change_bid: status_code={response.status_code}")
                return response.status_code == 201
            except: # noqa
                continue
        return False

    def bidder_info(self) -> list[Campaign]:
        self.log(f"{self.log_startswith}Сбор данных")
        campaigns: list[dict] = self.get_campaigns()
        campaigns: list[Campaign] = [Campaign.from_dict(campaign) for campaign in campaigns]

        for campaign in campaigns:
            rows = self.get_items(campaign.campaign_id)
            for row in rows:
                sku = row.get("sku_id")
                name = row.get("name")
                bid = round(row.get("bid", 0) / 100, 2)
                quantity = row.get("quantity")
                keywords = row.get("keywords", [])
                active = row.get("active")

                if all([name, sku]) and quantity is not None and active:
                    data = self.get_category(sku)[0]
                    category = data.get("name")
                    category_id = data.get("id")
                    children = data.get("children")

                    while isinstance(children, list):
                        category = children[0].get("name")
                        category_id = children[0].get("id")
                        children = children[0].get("children")

                    campaign.items.append(Item(
                        sku=sku,
                        name=name,
                        bid=bid,
                        quantity=quantity,
                        category=category,
                        category_id=category_id,
                        keywords=keywords
                    ))

        return campaigns

    def bidder(self, tasks: list[Task]) -> None:
        task_map = {}

        for task in tasks:
            if task.limit and task.position:
                task_map.setdefault((task.category_id, task.campaign_id), [])
                task_map[(task.category_id, task.campaign_id)].append(task)

        for value in task_map.values():
            value.sort(key=lambda x: x.position)

        for (category_id, _), items in task_map.items():
            for item in items:
                while item.position < 5:
                    self.log(f"{self.log_startswith}Обработка товара: {item}")

                    top_bids = self.get_top_bids(item)
                    if top_bids is None:
                        self.log(f"{self.log_startswith}Нет данных о ставках")
                        break

                    format_bid = int(item.bid / 10)
                    pos_bid = top_bids[item.position - 1]

                    if pos_bid == format_bid:
                        self.log(f"{self.log_startswith}Товар уже занимает позицию {item.position}")
                        break

                    bid_rub = (pos_bid + 1) * 10
                    self.log(
                        f"{self.log_startswith}Чтобы поднять товар до {item.position} "
                        f"нужно изменить ставку до {bid_rub}"
                    )

                    if bid_rub > item.limit:
                        self.log(
                            f"{self.log_startswith}Ставка позиции {bid_rub} больше лимита {item.limit}"
                        )
                        for item2 in items:
                            item2.position += 1
                        continue

                    self.log(
                        f"{self.log_startswith}Смена ставки, увеличение затрат на {bid_rub - item.bid}"
                    )

                    rows = self.get_items(item.campaign_id)

                    body = []
                    for row in rows:
                        sku = row.get("sku_id")
                        bid = row.get("bid")
                        keywords = row.get("keywords")
                        active = row.get("active")

                        if sku == item.sku:
                            bid = bid_rub * 100

                        body.append({
                            "active": active,
                            "bid": bid,
                            "keywords": keywords,
                            "sku_id": sku,
                        })

                    self.log(f"{self.log_startswith}Подготовлено тело запроса: {body}")

                    time.sleep(2)

                    # answer = self.change_bid(item.campaign_id, body)
                    # if answer:
                    #     self.log(f"{self.log_startswith}Смена прошла успешно")
                    # else:
                    #     self.log(f"{self.log_startswith}Что-то пошло не так")

                    break
                else:
                    self.log(f"{self.log_startswith}Позиция {item.position} больше лимита в 4")


    def load_url(self, url: str) -> None:
        self.log(f"{self.log_startswith}Браузер открыт")
        self.log(f"{self.log_startswith}Авторизация")
        self.driver.get(url)
        self.check_auth()

    def is_browser_active(self) -> bool:
        try:
            if self.driver.session_id is None:
                return False
            if not self.driver.service.is_connectable():
                return False
            return bool(self.driver.current_url)
        except (NoSuchWindowException, InvalidSessionIdException, WebDriverException):
            return False

    def quit(self, text: str = None) -> None:
        if text:
            self.log(f"{self.log_startswith}Ошибка автоматизации: {text}")
            self.driver.quit()
            raise AuthException(f"{text}\n\nПопробуйте позднее")
        else:
            self.log(f"{self.log_startswith}Браузер закрыт")
            self.driver.quit()
