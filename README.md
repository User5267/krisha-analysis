# Анализ рынка недвижимости Астаны

Пет-проект по построению полноценного data pipeline для анализа рынка недвижимости Астаны на основе данных с krisha.kz.

Основная цель — выяснить какие квартиры наиболее выгодны для инвестиций по сроку окупаемости.

---

## Архитектура

```
krisha.kz → Parser → CSV → Airflow → ClickHouse → dbt → Metabase
```

| Инструмент | Роль |
|------------|------|
| Python (requests, BeautifulSoup) | Парсинг объявлений с krisha.kz |
| Apache Airflow | Оркестрация — запуск парсера каждый день в 02:00 |
| ClickHouse | Хранилище данных |
| dbt | Трансформация: staging и mart слои |
| Metabase | Визуализация и дашборды |
| Docker | Все сервисы упакованы в контейнеры |

---

## Результаты

Анализ показал что **1-комнатные квартиры** наиболее выгодны для сдачи в аренду — срок окупаемости 10.4 лет при доходности 9.6% годовых.

| Комнат | Медиана продажи | Медиана аренды | Окупаемость | Доходность |
|--------|----------------|----------------|-------------|------------|
| 1 | 25 000 000 ₸ | 200 000 ₸/мес | 10.4 лет | 9.6% |
| 2 | 38 800 000 ₸ | 260 000 ₸/мес | 12.4 лет | 8.0% |
| 4 | 58 000 000 ₸ | 350 000 ₸/мес | 13.8 лет | 7.2% |

---

## Как запустить

### 1. Клонировать репозиторий
```bash
git clone https://github.com/твой_username/krisha-analysis.git
cd krisha-analysis
```

### 2. Запустить стек
```bash
docker compose up -d
```

### 3. Собрать образ парсера
```bash
docker compose build krisha-parser
```

### 4. Создать таблицу в ClickHouse
Подключиться к ClickHouse (порт 8123, user: admin) и выполнить SQL из файла `clickhouse/init/01_krisha_schema.sql`

### 5. Запустить парсер вручную (первый раз)
```bash
docker compose --profile manual run --rm krisha-parser --max-pages 50
```

### 6. Запустить Airflow DAG
Открыть `http://localhost:8080` (admin / admin123) и активировать DAG `krisha_pipeline`

### 7. Открыть дашборд
`http://localhost:3000` — Metabase с готовыми визуализациями

---

## Структура проекта

```
├── dags/
│   ├── krisha_parser.py      # Парсер krisha.kz
│   └── krisha_pipeline.py    # Airflow DAG
├── krisha_parser/
│   ├── Dockerfile
│   └── requirements.txt
├── my_dwh_project/           # dbt проект
│   └── models/
│       ├── staging/
│       │   └── stg_krisha.sql
│       └── marts/
│           ├── mart_price_by_rooms.sql
│           └── mart_payback.sql
├── data/                     # CSV от парсера
└── docker-compose.yml
```

---

## Технологии

- **Python 3.12** — парсинг (requests, BeautifulSoup, pandas)
- **Apache Airflow 2.9** — оркестрация
- **ClickHouse 24.3** — колоночное хранилище
- **dbt** — трансформация данных
- **Metabase** — визуализация
- **Docker + Docker Compose** — контейнеризация
