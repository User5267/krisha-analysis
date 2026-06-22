import time
import random
import logging
from typing import Optional
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


BASE_URL = "https://krisha.kz"

CATEGORIES = {
    "sale": {
        "url": f"{BASE_URL}/prodazha/kvartiry/astana/",
        "label": "sale",
        "description": "Продажа квартир — Астана",
    },
    "rent": {
        "url": f"{BASE_URL}/arenda/kvartiry/astana/",
        "label": "rent",
        "description": "Аренда квартир — Астана",
    },
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            # Без "br": если в окружении не установлен пакет brotli/brotlicffi,
            # requests не сможет раскодировать Brotli-ответ от сервера, и
            # resp.text окажется нечитаемой бинарной "кашей" (страница как бы
            # грузится с кодом 200, но карточки объявлений не находятся).
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": BASE_URL,
        }
    )
    return session


def get_page(
    session: requests.Session, url: str, retries: int = 3, delay: float = 2.0
) -> Optional[BeautifulSoup]:
    """Загружает страницу с повторными попытками и случайными паузами."""
    for attempt in range(retries):
        try:
            session.headers["User-Agent"] = random.choice(USER_AGENTS)
            time.sleep(delay + random.uniform(0.5, 1.5))
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            log.warning(f"Попытка {attempt + 1}/{retries} — ошибка: {e} | URL: {url}")
            time.sleep(delay * (attempt + 1))
    log.error(f"Не удалось загрузить страницу: {url}")
    return None

