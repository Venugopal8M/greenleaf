"""Analytics with pandas: revenue, top products, category share, slow movers, KPIs."""
from datetime import date, timedelta

import pandas as pd


def _sales_df(db, start, end):
    return pd.read_sql_query(
        "SELECT sale_id, sale_date, total_amount FROM sales WHERE sale_date BETWEEN ? AND ?",
        db, params=(start, end))


def _items_df(db, start, end):
    return pd.read_sql_query(
        """SELECT s.sale_date, i.sale_id, p.product_id, p.name, p.category,
                  i.quantity, i.quantity*i.price AS revenue
           FROM sale_items i JOIN sales s USING(sale_id) JOIN products p USING(product_id)
           WHERE s.sale_date BETWEEN ? AND ?""", db, params=(start, end))


def daily_sales(db, start, end):
    df = _sales_df(db, start, end)
    if df.empty:
        return []
    g = df.groupby("sale_date").agg(revenue=("total_amount", "sum"), bills=("sale_id", "count"))
    g["revenue"] = g["revenue"].round(2)
    return g.reset_index().rename(columns={"sale_date": "date"}).to_dict("records")


def monthly_sales(db, start, end):
    df = _sales_df(db, start, end)
    if df.empty:
        return []
    df["month"] = df["sale_date"].str[:7]
    g = df.groupby("month").agg(revenue=("total_amount", "sum"), bills=("sale_id", "count")).round(2)
    return g.reset_index().to_dict("records")


def top_products(db, start, end, n=10):
    df = _items_df(db, start, end)
    if df.empty:
        return []
    g = df.groupby("name").agg(quantity=("quantity", "sum"), revenue=("revenue", "sum")).round(2)
    return g.sort_values("revenue", ascending=False).head(n).reset_index().to_dict("records")


def category_share(db, start, end):
    df = _items_df(db, start, end)
    if df.empty:
        return []
    g = df.groupby("category").agg(quantity=("quantity", "sum"), revenue=("revenue", "sum")).round(2)
    g["share_pct"] = (g["revenue"] / g["revenue"].sum() * 100).round(1)
    return g.sort_values("revenue", ascending=False).reset_index().to_dict("records")


def slow_moving(db, days=30):
    """Products with little or no sales (<= 2 units) in the last `days` days."""
    since = (date.today() - timedelta(days=days)).isoformat()
    prods = pd.read_sql_query("SELECT product_id, name, category, stock_qty FROM products", db)
    items = pd.read_sql_query(
        "SELECT i.product_id, i.quantity FROM sale_items i JOIN sales s USING(sale_id) "
        "WHERE s.sale_date >= ?", db, params=(since,))
    sold = items.groupby("product_id")["quantity"].sum() if not items.empty else pd.Series(dtype=int)
    prods["units_sold"] = prods["product_id"].map(sold).fillna(0).astype(int)
    out = prods[(prods["units_sold"] <= 2) & (prods["stock_qty"] > 0)]
    return out.sort_values(["units_sold", "stock_qty"], ascending=[True, False]).to_dict("records")


def low_stock(db):
    return [dict(r) for r in db.execute(
        "SELECT product_id,name,category,stock_qty,reorder_level FROM products "
        "WHERE stock_qty <= reorder_level ORDER BY stock_qty - reorder_level")]


def expiring(db, days=15):
    return [dict(r) for r in db.execute(
        "SELECT product_id,name,category,stock_qty,expiry_date FROM products "
        "WHERE expiry_date IS NOT NULL AND expiry_date <= date('now', ?) ORDER BY expiry_date",
        (f"+{days} days",))]


def kpis(db, start, end):
    sales, items = _sales_df(db, start, end), _items_df(db, start, end)
    revenue = float(sales["total_amount"].sum()) if not sales.empty else 0.0
    bills = len(sales)
    units_sold = int(items["quantity"].sum()) if not items.empty else 0
    stock_units = db.execute("SELECT COALESCE(SUM(stock_qty),0) FROM products").fetchone()[0]
    cats = category_share(db, start, end)
    return {
        "total_revenue": round(revenue, 2),
        "bills": bills,
        "avg_bill_value": round(revenue / bills, 2) if bills else 0.0,
        # units sold in the period relative to units sold + units still on the shelf
        "stock_turnover": round(units_sold / (units_sold + stock_units), 2) if units_sold else 0.0,
        "low_stock_count": len(low_stock(db)),
        "top_category": cats[0]["category"] if cats else "-",
        "top_category_share": cats[0]["share_pct"] if cats else 0.0,
    }


def full_report(db, start, end):
    return {
        "kpis": kpis(db, start, end),
        "daily": daily_sales(db, start, end),
        "monthly": monthly_sales(db, start, end),
        "top": top_products(db, start, end),
        "categories": category_share(db, start, end),
        "slow": slow_moving(db),
        "low_stock": low_stock(db),
        "expiring": expiring(db),
    }
