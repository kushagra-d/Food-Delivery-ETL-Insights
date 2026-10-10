# Tableau dashboard: City Explorer

Build this in Tableau Desktop (free Tableau Public works too). Every file it needs is already in `tableau/data/`.

## 1. Connect the data

Connect to **Text file** and add these three files:

| File | Rows | Use it for |
|---|---|---|
| `orders_flat.csv` | 60,000 | Order-level KPIs: revenue, cancellations, delivery time, ratings |
| `restaurants.csv` | 400 | Restaurant-level map and price analysis |
| `restaurant_cuisines.csv` | 796 | Cuisine popularity (one row per restaurant per cuisine) |

On the Data Source tab, relate them on `restaurant_id`:
- `orders_flat` ↔ `restaurants`: relate on `restaurant_id`
- `orders_flat` ↔ `restaurant_cuisines`: relate on `restaurant_id`

Set `order_date` and `order_month` to **Date**. Set `lat` and `lon` to **Latitude** and **Longitude**.

## 2. Calculated fields

Create these with *Analysis → Create Calculated Field*:

```
Net Revenue (Delivered)
SUM(IF [Is Delivered] THEN [Net Revenue Inr] END)

Cancel Rate
SUM(IF [Status] = "Cancelled" THEN 1 ELSE 0 END) / COUNT([Order Id])

Revenue per Order
[Net Revenue (Delivered)] / COUNTD(IF [Is Delivered] THEN [Order Id] END)

Late Delivery Share
SUM(IF [Delivery Minutes] > 45 THEN 1 ELSE 0 END) / COUNT([Delivery Minutes])
```

Set the number formats: revenue as `₹#,##0`, rates as `0.0%`.

## 3. Sheets to build

1. **Map: revenue by city.** Double-click `Longitude` then `Latitude`. Drag `City` to Detail. Size = `Net Revenue (Delivered)`. Colour = `Cancel Rate`, using a diverging palette. Title: *Where the money and the cancellations are*.
2. **Bar: net revenue by city.** Columns = `Net Revenue (Delivered)`, Rows = `City`, sorted descending.
3. **Bar: rating by delivery time.** Columns = `Delivery Band`, Rows = `Avg(Rating)`. Set the band order to ≤20 min, 21-30, 31-45, 45+. Add a label to each bar. The 45+ band is the story.
4. **Bar: cuisine popularity.** Use the `restaurant_cuisines` source. Rows = `Cuisine`, Columns = `CNTD(Restaurant Id)`, sorted descending. Colour by `City` for the stacked view, or filter to one city.
5. **Scatter: price vs. rating.** Use `restaurants` joined to `orders_flat` on `restaurant_id`. Columns = `Avg Cost For Two`, Rows = `AVG(Rating)`, Detail = `Name`. Add a trend line. The correlation is near zero, which is the finding.
6. **Line: monthly net revenue.** Columns = `order_month` (month), Rows = `Net Revenue (Delivered)`.
7. **Heatmap: demand.** Columns = `Order Hour`, Rows = `Day Of Week`, Colour = `COUNT(Order Id)`.

## 4. Dashboard layout

*New Dashboard*, set size to *Automatic*.

```
+------------------------------+----------------------+
| KPI tiles: Revenue | Orders | Cancel rate | Rating  |
+------------------------------+----------------------+
| Map (city)                   | Revenue by city      |
+------------------------------+----------------------+
| Rating by delivery time | Cuisine popularity | Price scatter |
+---------------------------------------------------- +
| Monthly revenue               | Demand heatmap      |
+------------------------------+----------------------+
```

KPI tiles are **Text** sheets with `SUM` values in big font.

## 5. Filters and interactivity

- Add `City`, `Price Tier` and `order_month` (range) as **filters** on the dashboard. Apply them to all worksheets.
- *Dashboard → Actions → Add Action → Filter*: source = the map, target = all other sheets, run on Select. Clicking a city then drives the whole dashboard.

## 6. Story points

*Story* tab, three points:
1. "Mumbai leads revenue; Ahmedabad has the highest share of cafes (39% of restaurants)." Use sheets 1 and 4.
2. "Ratings fall as delivery time rises: 4.8 at ≤20 min, 3.6 at 45+ min." Use sheet 3.
3. "Price does not predict rating (r ≈ 0)." Use sheet 5.

## 7. Export and publish

- *File → Save As → Tableau Packaged Workbook (.twbx)*. Commit it to `tableau/`.
- *Server → Tableau Public → Save to Public Web* gives you a shareable link for your resume.
- Put the public link in the project README.
- Take a screenshot to `reports/figures/dashboard.png` for the README.
