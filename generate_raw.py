"""Generate a synthetic food-delivery dataset with realistic data-quality issues.

Replace data/raw/ with a real export (e.g. Kaggle Zomato/Swiggy) to run the same pipeline on real data.
"""
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).parent / "data" / "raw"
RNG = np.random.default_rng(42)

CITIES = {
    "Mumbai": 1.00, "Delhi": 0.95, "Bengaluru": 0.90, "Hyderabad": 0.70,
    "Chennai": 0.60, "Pune": 0.55, "Kolkata": 0.50, "Ahmedabad": 0.40,
}
CUISINES = ["North Indian", "South Indian", "Chinese", "Italian", "Fast Food",
            "Biryani", "Desserts", "Continental", "Mexican", "Cafe"]
PAYMENTS = ["UPI", "Card", "Cash", "Wallet"]
N_RESTAURANTS = 400
N_ORDERS = 60_000


def make_restaurants() -> pd.DataFrame:
    city_names = list(CITIES)
    city_w = np.array(list(CITIES.values()))
    rows = []
    for i in range(1, N_RESTAURANTS + 1):
        k = RNG.integers(1, 4)
        cuisines = RNG.choice(CUISINES, size=k, replace=False)
        rows.append({
            "restaurant_id": f"R{i:04d}",
            "name": f"Restaurant {i}",
            "city": RNG.choice(city_names, p=city_w / city_w.sum()),
            "cuisines": ", ".join(cuisines),
            "avg_cost_for_two": int(np.clip(RNG.lognormal(6.2, 0.45), 150, 3000)),
            "onboarded_on": pd.Timestamp("2022-01-01") + pd.to_timedelta(RNG.integers(0, 900), "D"),
        })
    df = pd.DataFrame(rows)

    # Messy inputs: inconsistent city spellings and casing, stray whitespace, missing costs
    variants = {"Bengaluru": ["bengaluru", "Bangalore", " Bengaluru "],
                "Mumbai": ["MUMBAI", "mumbai "], "Delhi": ["New Delhi", "delhi"]}
    for canon, alts in variants.items():
        mask = df["city"] == canon
        idx = df.index[mask]
        df.loc[RNG.choice(idx, size=len(idx) // 3, replace=False), "city"] = RNG.choice(alts, size=len(idx) // 3)
    missing = RNG.choice(df.index, size=12, replace=False)
    df.loc[missing, "avg_cost_for_two"] = np.nan
    return df


def make_orders(restaurants: pd.DataFrame) -> pd.DataFrame:
    rest_ids = restaurants["restaurant_id"].to_numpy()
    rest_pop = RNG.lognormal(0, 0.9, len(rest_ids))
    rest_pop = rest_pop / rest_pop.sum()
    cost = restaurants.set_index("restaurant_id")["avg_cost_for_two"].fillna(500)

    chosen = RNG.choice(rest_ids, size=N_ORDERS, p=rest_pop)
    order_ts = pd.Timestamp("2024-01-01") + pd.to_timedelta(RNG.integers(0, 366 * 24 * 60, N_ORDERS), "m")
    base_value = cost.loc[chosen].to_numpy() / 2 * RNG.lognormal(0, 0.35, N_ORDERS)
    distance = np.round(RNG.gamma(2.0, 2.2, N_ORDERS), 2)
    peak = pd.Series(order_ts.hour).isin([12, 13, 19, 20, 21]).to_numpy()
    eta = 18 + 3.5 * distance + 10 * peak + RNG.normal(0, 5, N_ORDERS)
    rating = np.clip(np.round(4.6 - 0.04 * (eta - 30) + RNG.normal(0, 0.6, N_ORDERS)), 1, 5)
    status = RNG.choice(["Delivered", "Cancelled"], size=N_ORDERS, p=[0.93, 0.07])

    orders = pd.DataFrame({
        "order_id": [f"O{i:07d}" for i in range(1, N_ORDERS + 1)],
        "order_ts": order_ts,
        "restaurant_id": chosen,
        "customer_id": [f"C{c:05d}" for c in RNG.integers(1, 15_000, N_ORDERS)],
        "order_value_inr": np.round(base_value, 2),
        "discount_inr": np.round(base_value * RNG.choice([0, 0, 0, 0.1, 0.2, 0.3], N_ORDERS), 2),
        "delivery_fee_inr": RNG.choice([0, 25, 40, 49], N_ORDERS, p=[0.3, 0.3, 0.25, 0.15]),
        "distance_km": distance,
        "delivery_minutes": np.round(eta, 1),
        "rating": rating,
        "payment_method": RNG.choice(PAYMENTS, N_ORDERS, p=[0.55, 0.25, 0.08, 0.12]),
        "status": status,
    })

    # Data-quality faults: missing ratings, impossible delivery times, duplicated rows
    orders.loc[RNG.choice(orders.index, 3_000, replace=False), "rating"] = np.nan
    orders.loc[RNG.choice(orders.index, 150, replace=False), "delivery_minutes"] = -1
    orders.loc[RNG.choice(orders.index, 80, replace=False), "delivery_minutes"] = 999
    orders = pd.concat([orders, orders.sample(400, random_state=7)], ignore_index=True)
    return orders


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    restaurants = make_restaurants()
    orders = make_orders(restaurants)
    restaurants.to_csv(RAW / "restaurants.csv", index=False)
    orders.to_csv(RAW / "orders.csv", index=False)
    print(f"restaurants: {len(restaurants):,} rows | orders: {len(orders):,} rows -> {RAW}")


if __name__ == "__main__":
    main()
