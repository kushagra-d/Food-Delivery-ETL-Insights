"""Cleaning and modelling. Every rule that drops or fixes rows is counted in the quality report."""
import re

import pandas as pd

CITY_CANONICAL = {
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru",
    "mumbai": "Mumbai", "new delhi": "Delhi", "delhi": "Delhi",
    "hyderabad": "Hyderabad", "chennai": "Chennai", "pune": "Pune",
    "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
}
CITY_COORDS = {  # lat/lon of each city centre, so Tableau can plot a map without geocoding
    "Mumbai": (19.076, 72.878), "Delhi": (28.614, 77.209), "Bengaluru": (12.972, 77.594),
    "Hyderabad": (17.385, 78.487), "Chennai": (13.083, 80.270), "Pune": (18.520, 73.856),
    "Kolkata": (22.573, 88.364), "Ahmedabad": (23.023, 72.572),
}
VALID_STATUSES = {"Delivered", "Cancelled"}
MAX_DELIVERY_MIN = 180


MONEY_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def parse_money(value) -> float:
    """Turn '₹1,200', 'Rs. 850' or 1200 into a float. Unparseable values become NaN."""
    if pd.isna(value):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    match = MONEY_PATTERN.search(str(value))
    return float(match.group().replace(",", "")) if match else float("nan")


def clean_restaurants(raw: pd.DataFrame, report: dict) -> pd.DataFrame:
    df = raw.copy()
    df["city_raw"] = df["city"]
    df["city"] = df["city"].str.strip().str.lower().map(CITY_CANONICAL)
    report["restaurants_unmapped_city"] = int(df["city"].isna().sum())
    df = df.dropna(subset=["city"])

    df["avg_cost_for_two"] = df["avg_cost_for_two"].map(parse_money)
    report["restaurants_missing_cost"] = int(df["avg_cost_for_two"].isna().sum())
    df["avg_cost_for_two"] = df["avg_cost_for_two"].fillna(
        df.groupby("city")["avg_cost_for_two"].transform("median")
    )
    df["cuisines"] = df["cuisines"].fillna("Unknown")
    df["primary_cuisine"] = df["cuisines"].str.split(",").str[0].str.strip()
    df["price_tier"] = pd.cut(df["avg_cost_for_two"], bins=[0, 300, 800, float("inf")],
                              labels=["Budget", "Mid", "Premium"])
    df["lat"] = df["city"].map(lambda c: CITY_COORDS[c][0])
    df["lon"] = df["city"].map(lambda c: CITY_COORDS[c][1])
    report["restaurants_clean"] = len(df)
    return df.drop(columns="city_raw")


def build_restaurant_cuisine(restaurants: pd.DataFrame) -> pd.DataFrame:
    """Bridge table: one row per restaurant per cuisine (multi-value field exploded and de-duplicated)."""
    bridge = (restaurants[["restaurant_id", "city", "cuisines"]]
              .assign(cuisine=lambda d: d["cuisines"].str.split(","))
              .explode("cuisine"))
    bridge["cuisine"] = bridge["cuisine"].str.strip().str.title()
    return bridge.drop_duplicates(subset=["restaurant_id", "cuisine"])[
        ["restaurant_id", "city", "cuisine"]].reset_index(drop=True)


def clean_orders(raw: pd.DataFrame, restaurants: pd.DataFrame, report: dict) -> pd.DataFrame:
    report["orders_raw"] = len(raw)

    df = raw.drop_duplicates(subset="order_id")
    report["orders_duplicates_removed"] = len(raw) - len(df)

    df = df[df["status"].isin(VALID_STATUSES)]
    bad_time = ~df["delivery_minutes"].between(1, MAX_DELIVERY_MIN) & df["status"].eq("Delivered")
    report["orders_invalid_delivery_time"] = int(bad_time.sum())
    df = df.assign(delivery_minutes=df["delivery_minutes"].mask(bad_time))

    orphan = ~df["restaurant_id"].isin(restaurants["restaurant_id"])
    report["orders_unknown_restaurant"] = int(orphan.sum())
    df = df[~orphan].copy()

    report["orders_missing_rating"] = int(df["rating"].isna().sum())

    df["order_ts"] = pd.to_datetime(df["order_ts"])
    df["order_date"] = df["order_ts"].dt.normalize()
    df["order_month"] = df["order_ts"].dt.to_period("M").dt.to_timestamp()
    df["order_hour"] = df["order_ts"].dt.hour
    df["day_of_week"] = df["order_ts"].dt.day_name()
    df["is_peak_hour"] = df["order_hour"].isin([12, 13, 19, 20, 21])
    df["is_delivered"] = df["status"].eq("Delivered")
    df["net_revenue_inr"] = (df["order_value_inr"] - df["discount_inr"]).clip(lower=0)
    df["gross_order_value_inr"] = df["order_value_inr"] + df["delivery_fee_inr"]
    df["delivery_band"] = pd.cut(df["delivery_minutes"], bins=[0, 20, 30, 45, MAX_DELIVERY_MIN],
                                 labels=["<=20 min", "21-30 min", "31-45 min", "45+ min"])
    df["distance_band"] = pd.cut(df["distance_km"], bins=[0, 2, 5, 10, float("inf")],
                                 labels=["0-2 km", "2-5 km", "5-10 km", "10+ km"])

    report["orders_clean"] = len(df)
    return df.reset_index(drop=True)


def build_dim_date(orders: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(orders["order_date"].min(), orders["order_date"].max(), freq="D")
    return pd.DataFrame({
        "date": dates,
        "year": dates.year,
        "month": dates.month,
        "month_name": dates.strftime("%b"),
        "week": dates.isocalendar().week.to_numpy(),
        "day_of_week": dates.day_name(),
        "is_weekend": dates.dayofweek >= 5,
    })
