"""
DAG: krisha_pipeline
Расписание: каждый день в 02:00 UTC (07:00 Астана)

Шаги:
  1. run_parser         — запускает krisha_parser.py через subprocess
  2. load_to_clickhouse — грузит CSV в ClickHouse
"""

from __future__ import annotations

import csv
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

log = logging.getLogger(__name__)

CLICKHOUSE_HOST     = "clickhouse"
CLICKHOUSE_PORT     = 9000
CLICKHOUSE_USER     = "admin"
CLICKHOUSE_PASSWORD = "admin123"
CLICKHOUSE_DB       = "krisha"
CLICKHOUSE_TABLE    = "raw_listings"
DATA_DIR            = "/opt/airflow/krisha_data"
PARSER_PATH         = "/opt/airflow/dags/krisha_parser.py"

COLUMNS = [
    "listing_type", "listing_id", "url", "title", "parsed_at",
    "price_raw", "price_tenge", "price_usd", "currency",
    "rooms", "area_total", "floor", "floors_total",
    "building_year", "building_type", "condition",
    "street", "address_raw", "description_snippet", "is_agency",
    "price_per_sqm_calc", "floor_ratio",
    "is_top_floor", "is_first_floor",
    "rooms_category", "building_era",
]

DEFAULT_ARGS = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="krisha_pipeline",
    default_args=DEFAULT_ARGS,
    description="Парсит krisha.kz и грузит данные в ClickHouse",
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["krisha", "real_estate"],
) as dag:

    def run_parser():
        os.makedirs(DATA_DIR, exist_ok=True)

        cmd = [
            sys.executable, PARSER_PATH,
            "--output-dir", DATA_DIR,
            "--max-pages", "50",
            "--delay", "2.0",
        ]

        log.info(f"Запускаю парсер: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,  # 2 часа максимум
        )

        if result.stdout:
            log.info(result.stdout)
        if result.stderr:
            log.info(result.stderr)

        if result.returncode != 0:
            raise Exception(f"Парсер завершился с ошибкой: код {result.returncode}")

        log.info("✅ Парсер завершился успешно")

    def load_csv_to_clickhouse():
        from clickhouse_driver import Client

        client = Client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            user=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DB,
        )

        def to_float(v):
            try:
                return float(v) if v not in ("", "None", None) else None
            except (ValueError, TypeError):
                return None

        def to_int(v):
            try:
                return int(float(v)) if v not in ("", "None", None) else None
            except (ValueError, TypeError):
                return None

        def to_uint8(v):
            return 1 if str(v).strip() in ("True", "1", "true") else 0

        def to_dt(v):
            if not v or v in ("None", ""):
                return datetime.now()
            try:
                return datetime.fromisoformat(v)
            except Exception:
                return datetime.now()

        def cast_row(row: dict) -> tuple:
            return (
                str(row.get("listing_type") or ""),
                str(row.get("listing_id") or ""),
                str(row.get("url") or ""),
                str(row.get("title") or ""),
                to_dt(row.get("parsed_at")),
                str(row.get("price_raw") or ""),
                to_float(row.get("price_tenge")),
                to_float(row.get("price_usd")),
                str(row.get("currency") or ""),
                to_int(row.get("rooms")),
                to_float(row.get("area_total")),
                to_int(row.get("floor")),
                to_int(row.get("floors_total")),
                to_int(row.get("building_year")),
                str(row.get("building_type") or ""),
                str(row.get("condition") or ""),
                str(row.get("street") or ""),
                str(row.get("address_raw") or ""),
                str(row.get("description_snippet") or ""),
                to_uint8(row.get("is_agency")),
                to_float(row.get("price_per_sqm_calc")),
                to_float(row.get("floor_ratio")),
                to_uint8(row.get("is_top_floor")),
                to_uint8(row.get("is_first_floor")),
                str(row.get("rooms_category") or ""),
                str(row.get("building_era") or ""),
            )

        total = 0
        for filename in ("krisha_sale.csv", "krisha_rent.csv"):
            filepath = os.path.join(DATA_DIR, filename)
            if not os.path.exists(filepath):
                log.warning(f"Файл не найден: {filepath}")
                continue

            rows = []
            with open(filepath, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    rows.append(cast_row(row))

            if not rows:
                log.warning(f"Файл пустой: {filepath}")
                continue

            col_str = ", ".join(COLUMNS)
            client.execute(
                f"INSERT INTO {CLICKHOUSE_DB}.{CLICKHOUSE_TABLE} ({col_str}) VALUES",
                rows,
            )
            log.info(f"✅ Загружено {len(rows)} строк из {filename}")
            total += len(rows)

        log.info(f"🎉 Итого: {total} строк в {CLICKHOUSE_DB}.{CLICKHOUSE_TABLE}")

    task_parse = PythonOperator(
        task_id="run_parser",
        python_callable=run_parser,
        execution_timeout=timedelta(hours=2),
    )

    task_load = PythonOperator(
        task_id="load_to_clickhouse",
        python_callable=load_csv_to_clickhouse,
    )

    task_parse >> task_load