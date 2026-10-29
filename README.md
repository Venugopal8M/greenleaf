# GreenLeaf Grocers – Inventory & Sales Management System

Flask + SQLite + pandas web app for products, stock, billing and sales analytics.

## Features
- Role-based login (admin: products, billing, reports; cashier: billing only), hashed passwords (werkzeug)
- Product CRUD, search/filter, CSV import and export, validation with friendly messages
- Billing: multi-item bills, discount %, automatic atomic stock deduction, printable bill and CSV download
- Dashboard + reports (Plotly charts, date-range selector, revenue/quantity toggle, CSV export)
- Alerts: low stock (stock <= reorder level) and expiring within 15 days
- KPIs: total revenue, average bill value, stock turnover, low-stock count, top category share
- 15 unit tests with a separate temporary database

## Setup
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python seed_data.py        # creates greenleaf.db: 56 products, 720 sales over ~6 months
python app.py              # open http://127.0.0.1:5000
```
Logins: `admin / admin123` and `cashier / cashier123`. Change them before any real use and set `SECRET_KEY`.

## Tests
```bash
python -m pytest -v        # or: python -m unittest discover tests
```

## Project layout
| File | Role |
|---|---|
| `app.py` | Flask app factory, error handlers |
| `database.py` | Schema (constraints, FKs, indexes) and connections |
| `models.py` | Users, product CRUD, billing logic |
| `routes.py` | Pages, JSON API, CSV downloads |
| `reports.py` | pandas analytics and KPIs |
| `utils.py` | Validation, role decorator, CSV import/export |
| `seed_data.py` | Demo data generator |
| `templates/`, `static/` | UI |

## ER diagram
```
suppliers 1──* products 1──* sale_items *──1 sales *──1 users
```
`sales.discount_pct` is stored on each bill; `sale_items.price` snapshots the price at sale time.
Tables are in 3NF: no repeated product data on bills, only IDs and the sold price.

## Design notes
- Revenue figures use `sales.total_amount` (after discount). Product and category charts use line amounts (before bill discount).
- Stock turnover = units sold in the period / (units sold + units currently in stock).
- Slow-moving = 2 units or fewer sold in the last 30 days and still in stock.
- Products that appear on past bills cannot be deleted, which keeps sales history intact.

## Screenshots
Run the app and add screenshots of the dashboard, products, billing and reports pages to a `screenshots/` folder.

## Ideas for bonus work
Sales forecasting (7-day moving average or Holt-Winters), barcode input, SMTP low-stock emails, Docker.
