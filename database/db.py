import time

from typing import Type
from functools import wraps
from datetime import datetime, timedelta

from pyodbc import Error as PyodbcError

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine, func as f

from config import DB_URL
from database.models import *


def retry_on_exception(retries: int = 3, delay: int = 5):

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            attempt = 0
            while attempt < retries:
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except (OperationalError, PyodbcError) as e:
                    attempt += 1
                    print(f"Повторная попытка {attempt}/{retries}")
                    time.sleep(delay)
                    if hasattr(self, 'session'):
                        self.session.rollback()
                except Exception as e:
                    print(f"База данных. Произошла непредвиденая ошибка: {str(e)}.")
                    if hasattr(self, 'session'):
                        self.session.rollback()
                    raise e
            raise RuntimeError("База данных. Попытки подключения исчерпаны")

        return wrapper

    return decorator


class DbConnection:

    def __init__(self, echo: bool = False) -> None:
        self.engine = create_engine(url=DB_URL,
                                    echo=echo,
                                    pool_size=10,
                                    max_overflow=5,
                                    pool_timeout=30,
                                    pool_recycle=1800,
                                    pool_pre_ping=True,
                                    connect_args={"keepalives": 1,
                                                  "keepalives_idle": 180,
                                                  "keepalives_interval": 60,
                                                  "keepalives_count": 20,
                                                  "connect_timeout": 10})
        self.session = Session(self.engine)

    @retry_on_exception()
    def get_market(self) -> Type[Market]:
        market = self.session.query(Market).filter_by(marketplace="МВидео").first()
        return market


    @retry_on_exception()
    def get_phone_message(self, user: str, phone: str, marketplace: str) -> str:
        check = None
        for _ in range(20):
            check = self.session.query(PhoneMessage).filter(
                f.lower(PhoneMessage.user) == user.lower(),
                PhoneMessage.phone == phone,
                PhoneMessage.marketplace == marketplace
            ).order_by(PhoneMessage.time_request.desc()).first()

            if check is None:
                raise Exception('Ошибка получения сообщения')

            if check.message is not None:
                return check.message

            self.session.expire(check)
            time.sleep(5)

        self.session.delete(check)
        self.session.commit()
        raise Exception("Превышен лимит ожидания сообщения")

    @retry_on_exception()
    def check_phone_message(self, user: str, phone: str, time_request: datetime) -> None:
        for _ in range(20):
            check = self.session.query(PhoneMessage).filter(
                PhoneMessage.phone == phone,
                PhoneMessage.time_request >= time_request - timedelta(minutes=2),
                PhoneMessage.time_response.is_(None)
            ).all()

            if any([row.user.lower() == user.lower() for row in check]):
                raise Exception("Предыдущая аторизация не завершена.")

            if not check:
                break

            self.session.expire(check)
            time.sleep(5)
        else:
            raise Exception("Превышен лимит ожидания очереди на авторизацию")

    @retry_on_exception()
    def add_phone_message(self, user: str, phone: str, marketplace: str, time_request: datetime) -> None:
        user = self.session.query(User).filter(f.lower(User.user) == user.lower()).first()
        if user is None:
            raise Exception("Такого пользователя не существует")

        new = PhoneMessage(user=user.user,
                           phone=phone,
                           marketplace=marketplace,
                           time_request=time_request)
        self.session.add(new)
        self.session.commit()
