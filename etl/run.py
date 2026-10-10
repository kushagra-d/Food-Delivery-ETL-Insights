"""Run the full pipeline: extract raw CSVs -> clean -> load star schema into SQLite and export Tableau extracts."""
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from etl.transform import build_dim_date, build_restaurant_cuisine, clean_orders, clean_restaurants

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
DB_PATH = PROCESSED / "food_delivery.db"

log = logging.getLogger("etl")


def extract() -> tuple[pd.DataFrame, pd.DataFrame]:
    restaurants = pd.read_csv(RAW / "restaurants.csv")
    orders = pd.read_csv(RAW / "orders.csv")
    log.info("extracted %d restaurants, %d orders", len(restaurants), len(orders))
    return restaurants, orders


def load(restaurants: pd.DataFrame, orders: pd.DataFrame, dim_date: pd.DataFrame,
         bridge: pd.DataFrame) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    dim_restaurant = restaurants[["restaurant_id", "name", "city", "primary_cuisine", "cuisines",
                                  "avg_cost_for_two", "price_tier", "lat", "lon", "onboarded_on"]]
    fact_cols = ["order_id", "order_ts", "order_date", "restaurant_id", "customer_id",
                 "order_value_inr", "discount_inr", "delivery_fee_inr", "net_revenue_inr",
                 "gross_order_value_inr", "distance_km", "distance_band", "delivery_minutes",
                 "delivery_band", "rating", "payment_method", "status", "is_delivered",
                 "order_hour", "is_peak_hour", "day_of_week", "order_month"]
    fact_orders = orders[fact_cols]

    with sqlite3.connect(DB_PATH) as con:
        dim_restaurant.to_sql("dim_restaurant", con, index=False)
        dim_date.to_sql("dim_date", con, index=False)
        fact_orders.to_sql("fact_orders", con, index=False)
        bridge.to_sql("bridge_restaurant_cuisine", con, index=False)
        con.executescript("""
            CREATE INDEX ix_fact_restaurant ON fact_orders(restaurant_id);
            CREATE INDEX ix_fact_date ON fact_orders(order_date);
            CREATE INDEX ix_bridge_cuisine ON bridge_restaurant_cuisine(cuisine);
            CREATE VIEW v_restaurant_kpis AS
            SELECT r.restaurant_id, r.name, r.city, r.primary_cuisine, r.price_tier,
                   COUNT(*) AS orders,
                   SUM(f.is_delivered) AS delivered_orders,
                   ROUND(AVG(f.rating), 2) AS avg_rating,
                   ROUND(AVG(f.delivery_minutes), 1) AS avg_delivery_minutes,
                   ROUND(SUM(CASE WHEN f.is_delivered THEN f.net_revenue_inr ELSE 0 END), 0) AS net_revenue_inr
            FROM fact_orders f JOIN dim_restaurant r USING (restaurant_id)
            GROUP BY r.restaurant_id;
        """)
    log.info("loaded star schema -> %s", DB_PATH)


def export_tableau(restaurants: pd.DataFrame, orders: pd.DataFrame, bridge: pd.DataFrame) -> None:
    tableau_dir = ROOT / "tableau" / "data"
    tableau_dir.mkdir(parents=True, exist_ok=True)
    flat = orders.merge(restaurants[["restaurant_id", "name", "city", "primary_cuisine", "price_tier",
                                     "avg_cost_for_two", "lat", "lon"]],
                        on="restaurant_id", how="left")
    flat.to_csv(tableau_dir / "orders_flat.csv", index=False)
    restaurants.to_csv(tableau_dir / "restaurants.csv", index=False)
    bridge.to_csv(tableau_dir / "restaurant_cuisines.csv", index=False)
    log.info("exported Tableau extracts: %d orders, %d restaurants, %d cuisine rows",
             len(flat), len(restaurants), len(bridge))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    report: dict = {}
    raw_restaurants, raw_orders = extract()
    restaurants = clean_restaurants(raw_restaurants, report)
    bridge = build_restaurant_cuisine(restaurants)
    report["restaurant_cuisine_pairs"] = len(bridge)
    orders = clean_orders(raw_orders, restaurants, report)
    dim_date = build_dim_date(orders)

    load(restaurants, orders, dim_date, bridge)
    export_tableau(restaurants, orders, bridge)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "quality_report.json").write_text(json.dumps(report, indent=2))
    log.info("quality report: %s", json.dumps(report))


if __name__ == "__main__":
    main()
