import pandas as pd


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

