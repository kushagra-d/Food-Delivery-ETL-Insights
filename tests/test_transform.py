"""Unit tests for the cleaning rules. Run with: python -m pytest"""
import math

import pandas as pd
import pytest

from etl.transform import build_restaurant_cuisine, clean_orders, clean_restaurants, parse_money


@pytest.mark.parametrize("raw, expected", [
    ("₹1,200", 1200.0),
    ("Rs. 850", 850.0),
    (640, 640.0),
    ("not a price", None),
    (None, None),
])
def test_parse_money(raw, expected):
    result = parse_money(raw)
    if expected is None:
        assert math.isnan(result)
    else:
        assert result == expected


def _restaurants() -> pd.DataFrame:
    return pd.DataFrame({
        "restaurant_id": ["R1", "R2", "R3"],
        "name": ["A", "B", "C"],
        "city": [" bangalore ", "Mumbai", "Atlantis"],
        "cuisines": ["Cafe, North Indian,cafe", "Biryani", "Chinese"],
        "avg_cost_for_two": ["₹600", None, "₹400"],
        "onboarded_on": ["2023-01-01"] * 3,
    }).pipe(lambda d: pd.concat([d, pd.DataFrame({
        # second Mumbai restaurant gives the city a median to fill R2's missing cost with
        "restaurant_id": ["R4"], "name": ["D"], "city": ["Mumbai"], "cuisines": ["Italian"],
        "avg_cost_for_two": ["₹900"], "onboarded_on": ["2023-01-01"],
    })], ignore_index=True))


def test_clean_restaurants_maps_cities_and_drops_unknown():
    report: dict = {}
    clean = clean_restaurants(_restaurants(), report)
    assert set(clean["city"]) == {"Bengaluru", "Mumbai"}
    assert report["restaurants_unmapped_city"] == 1


def test_clean_restaurants_fills_missing_cost_with_city_median():
    report: dict = {}
    clean = clean_restaurants(_restaurants(), report)
    assert clean["avg_cost_for_two"].notna().all()
    assert report["restaurants_missing_cost"] == 1


def test_bridge_explodes_and_dedupes_cuisines():
    clean = clean_restaurants(_restaurants(), {})
    bridge = build_restaurant_cuisine(clean)
    r1 = set(bridge.loc[bridge["restaurant_id"] == "R1", "cuisine"])
    assert r1 == {"Cafe", "North Indian"}  # 'cafe' duplicate collapsed, whitespace stripped


def test_clean_orders_nulls_impossible_delivery_times_and_dedupes():
    restaurants = clean_restaurants(_restaurants(), {})
    orders = pd.DataFrame({
        "order_id": ["O1", "O1", "O2", "O3"],
        "order_ts": ["2024-01-01 12:00", "2024-01-01 12:00", "2024-01-02 19:00", "2024-01-03 08:00"],
        "restaurant_id": ["R1", "R1", "R2", "R9"],  # R9 does not exist in the restaurant table
        "customer_id": ["C1"] * 4,
        "order_value_inr": [300.0, 300.0, 200.0, 100.0],
        "discount_inr": [0.0, 0.0, 20.0, 0.0],
        "delivery_fee_inr": [25, 25, 0, 0],
        "distance_km": [2.0, 2.0, 6.0, 1.0],
        "delivery_minutes": [30.0, 30.0, 999.0, 10.0],
        "rating": [4.0, 4.0, None, 5.0],
        "payment_method": ["UPI"] * 4,
        "status": ["Delivered", "Delivered", "Delivered", "Delivered"],
    })
    report: dict = {}
    clean = clean_orders(orders, restaurants, report)
    assert report["orders_duplicates_removed"] == 1
    assert report["orders_unknown_restaurant"] == 1
    assert report["orders_invalid_delivery_time"] == 1
    assert clean.loc[clean["order_id"] == "O2", "delivery_minutes"].isna().all()
    assert clean.loc[clean["order_id"] == "O2", "net_revenue_inr"].item() == 180.0
