import re
import time
import random
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

# ──────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Конфигурация URL
# ──────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────
# Структура объявления
# ──────────────────────────────────────────────────────────────────
@dataclass
class Listing:
    # Метаданные
    listing_type: str = ""          # sale | rent
    listing_id: str = ""
    url: str = ""
    title: str = ""
    parsed_at: str = ""

    # Цена
    price_raw: str = ""
    price_tenge: Optional[float] = None
    price_usd: Optional[float] = None
    price_per_sqm: Optional[float] = None
    currency: str = ""

    # Характеристики
    rooms: Optional[int] = None
    area_total: Optional[float] = None
    area_living: Optional[float] = None
    area_kitchen: Optional[float] = None
    floor: Optional[int] = None
    floors_total: Optional[int] = None
    building_year: Optional[int] = None
    building_type: str = ""         # кирпич, панель, монолит и т.д.
    condition: str = ""             # состояние / ремонт

    # Локация
    district: str = ""
    microdistrict: str = ""
    street: str = ""
    address_raw: str = ""

    # Дополнительно
    furniture: str = ""
    balcony: str = ""
    bathroom: str = ""
    parking: str = ""
    description_snippet: str = ""
    photos_count: Optional[int] = None
    is_agency: Optional[bool] = None


# ──────────────────────────────────────────────────────────────────
# HTTP сессия с ротацией User-Agent
# ──────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────
# Вспомогательные функции парсинга
# ──────────────────────────────────────────────────────────────────
def parse_price(text: str) -> dict:
    """Извлекает числовое значение цены и валюту."""
    if not text:
        return {"price_tenge": None, "price_usd": None, "currency": ""}
    raw = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    nums = re.findall(r"[\d.]+", raw)
    value = float(nums[0]) if nums else None
    if "₸" in text or "тг" in text.lower():
        return {"price_tenge": value, "price_usd": None, "currency": "KZT"}
    elif "$" in text or "usd" in text.lower():
        return {"price_tenge": None, "price_usd": value, "currency": "USD"}
    return {"price_tenge": value, "price_usd": None, "currency": "KZT"}


def extract_int(text: str) -> Optional[int]:
    m = re.search(r"\d+", str(text).replace("\xa0", ""))
    return int(m.group()) if m else None


def extract_float(text: str) -> Optional[float]:
    m = re.search(r"[\d.,]+", str(text).replace("\xa0", "").replace(",", "."))
    return float(m.group()) if m else None


# ──────────────────────────────────────────────────────────────────
# Парсинг карточки объявления (страница списка)
# ──────────────────────────────────────────────────────────────────
def parse_card(card, listing_type: str) -> Listing:
    """Парсит одну карточку из списка объявлений."""
    item = Listing()
    item.listing_type = listing_type
    item.parsed_at = pd.Timestamp.now().isoformat()

    # ID — берём напрямую из атрибута data-id контейнера карточки
    # (актуальная разметка: <div class="a-card ..." data-id="1013047465">).
    item.listing_id = (
        card.get("data-id") or card.get("data-product-id") or ""
    )

    # Заголовок и URL.
    # Текущая разметка: <a class="a-card__title" href="/a/show/1013047465">
    #     3-комнатная квартира · 73 м² · 9/9 этаж
    # </a>
    a_tag = card.select_one("a.a-card__title")
    if not a_tag:
        a_tag = card.find("a", href=re.compile(r"/a/show/"))
    if a_tag:
        href = a_tag.get("href", "")
        item.url = BASE_URL + href if href.startswith("/") else href
        item.title = a_tag.get_text(strip=True)

        if not item.listing_id:
            m = re.search(r"/a/show/(\d+)", href)
            item.listing_id = m.group(1) if m else ""

        # Комнаты / площадь / этаж сейчас "склеены" в заголовке, например:
        # "3-комнатная квартира · 73 м² · 9/9 этаж"
        title_text = item.title

        m = re.search(r"(\d+)-комн", title_text)
        if m:
            item.rooms = int(m.group(1))

        m = re.search(r"([\d.,]+)\s*м²", title_text)
        if m:
            item.area_total = float(m.group(1).replace(",", "."))

        m = re.search(r"(\d+)/(\d+)\s*эт", title_text)
        if m:
            item.floor = int(m.group(1))
            item.floors_total = int(m.group(2))

    # Цена: <div class="a-card__price">50 500 000 <span class="currency-sign ...">₸</span></div>
    price_tag = card.select_one(".a-card__price")
    if price_tag:
        item.price_raw = price_tag.get_text(" ", strip=True)
        pdata = parse_price(item.price_raw)
        item.price_tenge = pdata["price_tenge"]
        item.price_usd = pdata["price_usd"]
        item.currency = pdata["currency"]

    # Подзаголовок — улица / название ЖК и т.п.:
    # <div class="a-card__subtitle">Толе Би 22 — ВОЗМОЖНА ИПОТЕКА!!!</div>
    address_tag = card.select_one(".a-card__subtitle")
    if address_tag:
        address_text = address_tag.get_text(" ", strip=True)
        item.address_raw = address_text
        item.street = address_text

    # Описание (сниппет): <div class="a-card__text-preview">жил. комплекс ...</div>
    desc_tag = card.select_one(".a-card__text-preview")
    if desc_tag:
        item.description_snippet = desc_tag.get_text(strip=True)[:300]

    # Агентство vs частное лицо — определяем по наличию метки
    # "Крыша Агент" / "Личность подтверждена" и т.п. в блоке владельца.
    agency_tag = card.select_one(
        ".a-card__owner .label-user-agent, "
        ".a-card__owner [class*='user-title-pro'], "
        ".a-card__owner [class*='identified']"
    )
    item.is_agency = agency_tag is not None

    return item


# ──────────────────────────────────────────────────────────────────
# Парсинг страницы деталей объявления (опционально — для обогащения)
# ──────────────────────────────────────────────────────────────────
def enrich_listing(
    session: requests.Session, item: Listing
) -> Listing:
    """Заходит на страницу объявления и дополняет данные."""
    if not item.url:
        return item

    soup = get_page(session, item.url, delay=1.5)
    if not soup:
        return item

    # Параметры из таблицы характеристик
    for row in soup.select(".offer__parameters .offer__parameter, [class*='offer-params'] li"):
        label_el = row.select_one(".offer__parameter-title, [class*='label']")
        value_el = row.select_one(".offer__parameter-value, [class*='value']")
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True).lower()
        value = value_el.get_text(strip=True)

        if "площадь" in label and "общ" in label:
            item.area_total = extract_float(value)
        elif "площадь" in label and "жил" in label:
            item.area_living = extract_float(value)
        elif "площадь" in label and "кухн" in label:
            item.area_kitchen = extract_float(value)
        elif "этаж" in label and "этажей" not in label:
            item.floor = extract_int(value)
        elif "этажей" in label or "этажность" in label:
            item.floors_total = extract_int(value)
        elif "год" in label and "постр" in label:
            item.building_year = extract_int(value)
        elif "тип" in label and ("дом" in label or "здан" in label or "строен" in label):
            item.building_type = value
        elif "состоян" in label or "ремонт" in label:
            item.condition = value
        elif "мебел" in label:
            item.furniture = value
        elif "балкон" in label or "лоджи" in label:
            item.balcony = value
        elif "санузел" in label or "ванн" in label:
            item.bathroom = value
        elif "парков" in label or "гараж" in label:
            item.parking = value

    # Цена за м²
    sqm_tag = soup.select_one("[class*='per-m2'], [class*='price-per-sqm']")
    if sqm_tag:
        item.price_per_sqm = extract_float(sqm_tag.get_text())

    # Район / микрорайон из breadcrumb или адресного блока
    breadcrumbs = soup.select(".breadcrumb a, [class*='breadcrumb'] a")
    if breadcrumbs:
        texts = [b.get_text(strip=True) for b in breadcrumbs]
        # Обычно: Астана > Район > Микрорайон
        if len(texts) > 2:
            item.district = texts[-2]
        if len(texts) > 3:
            item.microdistrict = texts[-1]

    # Полный адрес
    addr_tag = soup.select_one("[class*='offer-address'], .offer__address")
    if addr_tag:
        item.address_raw = addr_tag.get_text(" ", strip=True)

    return item


# ──────────────────────────────────────────────────────────────────
# Пагинация и сбор списка объявлений
# ──────────────────────────────────────────────────────────────────
def get_total_pages(soup: BeautifulSoup) -> int:
    """Определяет общее количество страниц пагинации."""
    import math

    # Вариант 1: заголовок вида "Найдено 38 514 объявлений"
    page_text = soup.get_text(" ", strip=True)
    m = re.search(r"Найдено\s*([\d\s\u00a0]+)\s*объявлен", page_text)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        if digits:
            total_count = int(digits)
            items_per_page = 20
            return math.ceil(total_count / items_per_page)

    # Вариант 2: ищем максимальный номер страницы среди ссылок ?page=N
    page_nums = []
    for a in soup.select("a[href*='page=']"):
        m = re.search(r"page=(\d+)", a.get("href", ""))
        if m:
            page_nums.append(int(m.group(1)))
    if page_nums:
        return max(page_nums)

    return 1


def scrape_category(
    session: requests.Session,
    base_url: str,
    label: str,
    max_pages: int = 50,
    enrich: bool = False,
    delay: float = 2.0,
) -> list[Listing]:
    """Собирает все объявления по одной категории (продажа или аренда)."""
    listings: list[Listing] = []

    log.info(f"🔍 Загружаю первую страницу: {base_url}")
    first_page = get_page(session, base_url, delay=delay)
    if not first_page:
        log.error("Не удалось загрузить первую страницу!")
        return listings

    total_pages = min(get_total_pages(first_page), max_pages)
    log.info(f"📄 Страниц для парсинга: {total_pages} (лимит: {max_pages})")

    def parse_page_listings(soup, lt):
        """
        Поиск карточек объявлений. 
        Используем селектор по атрибуту data-id, который есть у каждой карточки.
        """
        # Список возможных селекторов для поиска контейнеров карточек.
        # Актуальная разметка (2026): <div class="a-card ..." data-id="...">
        selectors = [
            "div.a-card[data-id]",
            "div[data-id]",
            "article[data-id]",
        ]
        
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break
                
        if not cards:
            log.warning("⚠️ Карточки не найдены — возможно, изменилась структура сайта")
            return []

        results = []
        for card in cards:
            # Важно: отфильтровываем рекламные/служебные блоки, если они имеют
            # data-id, но не являются настоящими карточками объявлений
            # (например, без ссылки на /a/show/...).
            try:
                parsed = parse_card(card, lt)
                if parsed and parsed.listing_id:
                    results.append(parsed)
            except Exception as e:
                continue
                
        return results

    # Первая страница
    page_listings = parse_page_listings(first_page, label)
    listings.extend(page_listings)
    log.info(f"   Стр. 1/{total_pages} — найдено {len(page_listings)} объявлений")

    # Остальные страницы
    for page_num in tqdm(range(2, total_pages + 1), desc=f"{label.upper()} страницы"):
        url = f"{base_url}?page={page_num}"
        soup = get_page(session, url, delay=delay)
        if not soup:
            continue
        page_listings = parse_page_listings(soup, label)
        listings.extend(page_listings)
        log.info(f"   Стр. {page_num}/{total_pages} — +{len(page_listings)} (всего {len(listings)})")

    # Опциональное обогащение (заход на каждую страницу объявления)
    if enrich and listings:
        log.info(f"\n🔗 Обогащение данных — захожу на каждое объявление ({len(listings)} шт.)...")
        for item in tqdm(listings, desc="Обогащение"):
            enrich_listing(session, item)

    return listings


# ──────────────────────────────────────────────────────────────────
# Постобработка датасета
# ──────────────────────────────────────────────────────────────────
def postprocess(df: pd.DataFrame) -> pd.DataFrame:
    """Чистка, типизация, добавление расчётных колонок."""

    # Числовые типы
    num_cols = [
        "price_tenge", "price_usd", "price_per_sqm",
        "area_total", "area_living", "area_kitchen",
        "floor", "floors_total", "building_year", "rooms", "photos_count",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Удаляем дубликаты по listing_id
    df.drop_duplicates(subset=["listing_id"], keep="first", inplace=True)

    # Фильтрация аномалий
    if "price_tenge" in df.columns:
        df = df[
            (df["price_tenge"].isna()) |
            ((df["price_tenge"] > 100_000) & (df["price_tenge"] < 10_000_000_000))
        ]
    if "area_total" in df.columns:
        df = df[
            (df["area_total"].isna()) |
            ((df["area_total"] > 10) & (df["area_total"] < 1000))
        ]

    # Расчётные колонки
    if "price_tenge" in df.columns and "area_total" in df.columns:
        df["price_per_sqm_calc"] = (df["price_tenge"] / df["area_total"]).round(0)

    if "floor" in df.columns and "floors_total" in df.columns:
        df["floor_ratio"] = (df["floor"] / df["floors_total"]).round(3)
        df["is_top_floor"] = df["floor"] == df["floors_total"]
        df["is_first_floor"] = df["floor"] == 1

    # Категория комнатности
    if "rooms" in df.columns:
        df["rooms_category"] = df["rooms"].map(
            {1: "1-комн", 2: "2-комн", 3: "3-комн", 4: "4-комн"}
        ).fillna("5+ комн")

    # Год постройки → период
    if "building_year" in df.columns:
        bins = [0, 1960, 1990, 2000, 2010, 2020, 2030]
        labels = ["до 1960", "1960-1990", "1990-2000", "2000-2010", "2010-2020", "после 2020"]
        df["building_era"] = pd.cut(df["building_year"], bins=bins, labels=labels, right=True)

    return df


# ──────────────────────────────────────────────────────────────────
# Основная функция
# ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Krisha.kz парсер — Астана")
    parser.add_argument("--max-pages", type=int, default=50, help="Макс. кол-во страниц на категорию")
    parser.add_argument("--enrich", action="store_true", help="Заходить на каждое объявление для полных данных")
    parser.add_argument("--delay", type=float, default=2.0, help="Базовая задержка между запросами (сек)")
    parser.add_argument("--output-dir", type=str, default=".", help="Папка для сохранения CSV")
    parser.add_argument("--only", choices=["sale", "rent"], help="Парсить только одну категорию")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = make_session()
    all_data: dict[str, list[Listing]] = {}

    # Выбор категорий
    cats_to_parse = (
        {k: v for k, v in CATEGORIES.items() if k == args.only}
        if args.only
        else CATEGORIES
    )

    for cat_key, cat_info in cats_to_parse.items():
        log.info(f"\n{'='*60}")
        log.info(f"  Категория: {cat_info['description']}")
        log.info(f"  URL: {cat_info['url']}")
        log.info(f"{'='*60}\n")

        listings = scrape_category(
            session=session,
            base_url=cat_info["url"],
            label=cat_info["label"],
            max_pages=args.max_pages,
            enrich=args.enrich,
            delay=args.delay,
        )

        if not listings:
            log.warning(f"Нет данных для категории {cat_key}!")
            continue

        # В датафрейм
        df = pd.DataFrame([asdict(l) for l in listings])
        df = postprocess(df)
        all_data[cat_key] = df

        # Сохраняем CSV
        out_path = output_dir / f"krisha_{cat_key}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        log.info(f"\n✅ Сохранено {len(df)} записей → {out_path}")
        log.info(df[["listing_type", "rooms", "area_total", "floor", "price_tenge", "address_raw"]].head(5).to_string())

    # Объединённый датасет
    if len(all_data) > 1:
        combined = pd.concat(list(all_data.values()), ignore_index=True)
        combined_path = output_dir / "krisha_combined.csv"
        combined.to_csv(combined_path, index=False, encoding="utf-8-sig")
        log.info(f"\n🗂  Объединённый датасет: {len(combined)} записей → {combined_path}")

        # Мини-отчёт
        log.info("\n📊 Краткая статистика:")
        for ltype, grp in combined.groupby("listing_type"):
            log.info(f"\n  [{ltype.upper()}]")
            log.info(f"  Записей: {len(grp)}")
            if grp["price_tenge"].notna().any():
                log.info(f"  Цена (тг): {grp['price_tenge'].describe()[['mean','min','max']].to_dict()}")
            if grp["area_total"].notna().any():
                log.info(f"  Площадь м²: {grp['area_total'].describe()[['mean','min','max']].to_dict()}")

    log.info("\n🎉 Парсинг завершён!")


if __name__ == "__main__":
    main()
