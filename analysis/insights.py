"""Query the SQLite warehouse, produce analysis charts, and write a key-findings summary."""
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "food_delivery.db"
FIG = ROOT / "reports" / "figures"

sns.set_theme(style="whitegrid", context="talk")
PALETTE = "crest"


def query(sql: str) -> pd.DataFrame:
    with sqlite3.connect(DB) as con:
        return pd.read_sql(sql, con)


def monthly_trend() -> pd.DataFrame:
    df = query("""
        SELECT order_month AS month,
               COUNT(*) AS orders,
               ROUND(SUM(CASE WHEN is_delivered THEN net_revenue_inr ELSE 0 END) / 1e5, 2) AS net_revenue_lakh,
               ROUND(AVG(rating), 2) AS avg_rating
        FROM fact_orders GROUP BY order_month ORDER BY order_month
    """)
    df["month"] = pd.to_datetime(df["month"])  # SQLite returns text; plot needs real dates
    return df


def city_summary() -> pd.DataFrame:
    return query("""
        SELECT r.city,
               COUNT(*) AS orders,
               ROUND(100.0 * SUM(1 - f.is_delivered) / COUNT(*), 2) AS cancel_rate_pct,
               ROUND(AVG(f.delivery_minutes), 1) AS avg_delivery_min,
               ROUND(AVG(f.rating), 2) AS avg_rating,
               ROUND(SUM(CASE WHEN f.is_delivered THEN f.net_revenue_inr ELSE 0 END) / 1e5, 1) AS net_revenue_lakh
        FROM fact_orders f JOIN dim_restaurant r USING (restaurant_id)
        GROUP BY r.city ORDER BY net_revenue_lakh DESC
    """)


DELIVERY_BANDS = ["<=20 min", "21-30 min", "31-45 min", "45+ min"]


def delivery_vs_rating() -> pd.DataFrame:
    df = query("""
        SELECT delivery_band, ROUND(AVG(rating), 2) AS avg_rating, COUNT(rating) AS rated_orders
        FROM fact_orders WHERE is_delivered AND delivery_band IS NOT NULL AND rating IS NOT NULL
        GROUP BY delivery_band
    """)
    df["delivery_band"] = pd.Categorical(df["delivery_band"], DELIVERY_BANDS, ordered=True)
    return df.sort_values("delivery_band").reset_index(drop=True)


def order_heatmap() -> pd.DataFrame:
    df = query("SELECT day_of_week, order_hour, COUNT(*) AS orders FROM fact_orders GROUP BY 1, 2")
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return df.pivot(index="day_of_week", columns="order_hour", values="orders").reindex(order)


def price_tier_rating() -> pd.DataFrame:
    return query("""
        SELECT r.price_tier, ROUND(AVG(f.rating), 2) AS avg_rating,
               ROUND(AVG(f.delivery_minutes), 1) AS avg_delivery_min, COUNT(*) AS orders
        FROM fact_orders f JOIN dim_restaurant r USING (restaurant_id)
        WHERE f.is_delivered GROUP BY r.price_tier
    """)


def cuisine_by_city() -> pd.DataFrame:
    """Share of each city's restaurants offering each cuisine, using the exploded bridge table."""
    df = query("""
        SELECT b.city, b.cuisine, COUNT(DISTINCT b.restaurant_id) AS restaurants,
               COUNT(f.order_id) AS orders
        FROM bridge_restaurant_cuisine b
        LEFT JOIN fact_orders f USING (restaurant_id)
        GROUP BY b.city, b.cuisine
    """)
    return df


def price_vs_rating() -> pd.DataFrame:
    return query("""
        SELECT r.restaurant_id, r.city, r.price_tier, r.avg_cost_for_two,
               ROUND(AVG(f.rating), 2) AS avg_rating, COUNT(f.rating) AS rated_orders
        FROM dim_restaurant r JOIN fact_orders f USING (restaurant_id)
        WHERE f.is_delivered AND f.rating IS NOT NULL
        GROUP BY r.restaurant_id
    """)


def plot_all() -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    trend = monthly_trend()
    fig, ax = plt.subplots(figsize=(12, 5.5))
    sns.lineplot(data=trend, x="month", y="net_revenue_lakh", marker="o", linewidth=2.5, ax=ax, color="#2a9d8f")
    ax.set(title="Monthly net revenue (INR lakh), 2024", xlabel="", ylabel="Net revenue (INR lakh)")
    ax.fill_between(trend["month"], trend["net_revenue_lakh"], alpha=0.15, color="#2a9d8f")
    ax.set_xticks(trend["month"], trend["month"].dt.strftime("%b"))
    fig.tight_layout(); fig.savefig(FIG / "01_monthly_revenue.png", dpi=150); plt.close(fig)

    cities = city_summary()
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(data=cities, y="city", x="net_revenue_lakh", hue="city", legend=False, palette=PALETTE, ax=ax)
    ax.set(title="Net revenue by city (INR lakh)", xlabel="Net revenue (INR lakh)", ylabel="")
    for p, v in zip(ax.patches, cities["net_revenue_lakh"]):
        ax.text(p.get_width() + 0.3, p.get_y() + p.get_height() / 2, f"{v:.0f}", va="center")
    fig.tight_layout(); fig.savefig(FIG / "02_city_revenue.png", dpi=150); plt.close(fig)

    dvr = delivery_vs_rating()
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=dvr, x="delivery_band", y="avg_rating", hue="delivery_band", legend=False,
                palette=PALETTE, ax=ax)
    ax.set(title="Customer rating drops as delivery time grows", xlabel="Delivery time", ylabel="Average rating",
           ylim=(0, 5))
    for p, v in zip(ax.patches, dvr["avg_rating"]):
        ax.text(p.get_x() + p.get_width() / 2, v + 0.1, f"{v:.2f}", ha="center")
    fig.tight_layout(); fig.savefig(FIG / "03_delivery_vs_rating.png", dpi=150); plt.close(fig)

    heat = order_heatmap()
    fig, ax = plt.subplots(figsize=(14, 5.5))
    sns.heatmap(heat, cmap="mako", ax=ax, cbar_kws={"label": "Orders"})
    ax.set(title="Order demand by day and hour", xlabel="Hour of day", ylabel="")
    fig.tight_layout(); fig.savefig(FIG / "04_demand_heatmap.png", dpi=150); plt.close(fig)

    tiers = price_tier_rating()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    order = ["Budget", "Mid", "Premium"]
    sns.barplot(data=tiers, x="price_tier", y="avg_rating", order=order, hue="price_tier", legend=False,
                palette=PALETTE, ax=axes[0])
    axes[0].set(title="Avg rating by price tier", xlabel="", ylabel="Average rating", ylim=(0, 5))
    sns.barplot(data=tiers, x="price_tier", y="avg_delivery_min", order=order, hue="price_tier", legend=False,
                palette=PALETTE, ax=axes[1])
    axes[1].set(title="Avg delivery time by price tier", xlabel="", ylabel="Minutes")
    fig.tight_layout(); fig.savefig(FIG / "05_price_tier.png", dpi=150); plt.close(fig)

    cuisines = cuisine_by_city()
    city_totals = query("SELECT city, COUNT(*) AS n FROM dim_restaurant GROUP BY city").set_index("city")["n"]
    share = cuisines.pivot(index="cuisine", columns="city", values="restaurants").fillna(0)
    share = (100 * share / city_totals.reindex(share.columns)).round(1)
    share = share.loc[share.mean(axis=1).sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(12, 7))
    sns.heatmap(share, annot=True, fmt=".0f", cmap="crest", ax=ax, cbar_kws={"label": "% of city's restaurants"})
    ax.set(title="Cuisine presence by city (% of restaurants offering it)", xlabel="", ylabel="")
    fig.tight_layout(); fig.savefig(FIG / "06_cuisine_by_city.png", dpi=150); plt.close(fig)

    pr = price_vs_rating()
    fig, ax = plt.subplots(figsize=(11, 6.5))
    sns.regplot(data=pr, x="avg_cost_for_two", y="avg_rating", scatter_kws={"alpha": 0.5, "s": 28},
                line_kws={"color": "#e76f51"}, ax=ax)
    ax.set(title="Restaurant price vs. rating", xlabel="Avg cost for two (INR)", ylabel="Average rating",
           ylim=(1, 5))
    fig.tight_layout(); fig.savefig(FIG / "07_price_vs_rating.png", dpi=150); plt.close(fig)


def write_summary() -> None:
    cities = city_summary()
    dvr = delivery_vs_rating()
    pr = price_vs_rating()
    r = np.corrcoef(pr["avg_cost_for_two"], pr["avg_rating"])[0, 1]
    cuisines = cuisine_by_city().groupby("cuisine")["restaurants"].sum().sort_values(ascending=False)
    top = query("""
        SELECT r.name, r.city, r.primary_cuisine, orders, avg_rating, net_revenue_inr
        FROM v_restaurant_kpis r WHERE orders >= 100
        ORDER BY net_revenue_inr DESC LIMIT 10
    """)
    worst_cancel = cities.sort_values("cancel_rate_pct", ascending=False).iloc[0]
    fastest = dvr.iloc[0]
    slowest = dvr.iloc[-1]
    worst_band = dvr.loc[dvr["avg_rating"].idxmin()]
    lines = [
        "# Key findings",
        "",
        f"- Highest-revenue city: **{cities.iloc[0]['city']}** ({cities.iloc[0]['net_revenue_lakh']:.0f} lakh).",
        f"- Highest cancellation rate: **{worst_cancel['city']}** ({worst_cancel['cancel_rate_pct']:.1f}%).",
        f"- Average rating is **{fastest['avg_rating']:.2f}** for {fastest['delivery_band']} deliveries and "
        f"**{slowest['avg_rating']:.2f}** for {slowest['delivery_band']} deliveries "
        f"(lowest band: {worst_band['delivery_band']} at {worst_band['avg_rating']:.2f}).",
        f"- Price vs. rating correlation across {len(pr)} restaurants: **r = {r:+.2f}** "
        "(near zero means price does not predict customer rating).",
        f"- Most common cuisine across the network: **{cuisines.index[0]}** "
        f"({cuisines.iloc[0]} restaurant listings).",
        "",
        "## Top 10 restaurants by net revenue (min. 100 orders)",
        "",
        top.to_markdown(index=False),
        "",
    ]
    (ROOT / "reports" / "key_findings.md").write_text("\n".join(lines))


if __name__ == "__main__":
    plot_all()
    write_summary()
    print("charts ->", FIG)
