def run_scraper():
    print("Парсинг...")
    import argparse
    from pathlib import Path
    from dataclasses import asdict
    import pandas as pd
    from http_client import make_session, CATEGORIES, log
    from structure import Listing 
    from dags.krisha_parser import scrape_category 
    from postprocess import postprocess



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

    return "Done."