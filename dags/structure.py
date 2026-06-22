from dataclasses import dataclass
from typing import Optional

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
