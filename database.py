"""Database layer: schema, connections and helpers (SQLite)."""
import sqlite3
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','cashier')));
CREATE TABLE IF NOT EXISTS suppliers(
  supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, phone TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS products(
  product_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  unit_price REAL NOT NULL CHECK(unit_price >= 0),
  stock_qty INTEGER NOT NULL DEFAULT 0 CHECK(stock_qty >= 0),
  reorder_level INTEGER NOT NULL DEFAULT 10 CHECK(reorder_level >= 0),
  expiry_date TEXT,
  supplier_id INTEGER REFERENCES suppliers(supplier_id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS sales(
  sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_date TEXT NOT NULL,
  sale_time TEXT NOT NULL,
  user_id INTEGER NOT NULL REFERENCES users(user_id),
  discount_pct REAL NOT NULL DEFAULT 0 CHECK(discount_pct BETWEEN 0 AND 100),
  total_amount REAL NOT NULL CHECK(total_amount >= 0));
CREATE TABLE IF NOT EXISTS sale_items(
  sale_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id INTEGER NOT NULL REFERENCES sales(sale_id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(product_id),
  quantity INTEGER NOT NULL CHECK(quantity > 0),
  price REAL NOT NULL CHECK(price >= 0));
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_items_product ON sale_items(product_id);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
