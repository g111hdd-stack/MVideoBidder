import logging
from typing import Callable


class GuiCallbackHandler(logging.Handler):
    def __init__(self, callback: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self._callback = callback

    def set_callback(self, callback: Callable[[str], None] | None) -> None:
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        if self._callback is None:
            return

        try:
            message = self.format(record)
            self._callback(message)
        except: # noqa
            pass


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("mvideo_bidder")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    gui_handler = GuiCallbackHandler()
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(formatter)

    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(gui_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger


def set_gui_logger_callback(callback: Callable[[str], None] | None) -> None:
    logger = logging.getLogger("mvideo_bidder")
    for handler in logger.handlers:
        if isinstance(handler, GuiCallbackHandler):
            handler.set_callback(callback)
            break