"""Business logic: users, products and billing."""
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash


# ---------- users ----------
def create_user(db, username, password, role):
    db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
               (username, generate_password_hash(password), role))
    db.commit()


def authenticate(db, username, password):
    row = db.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
    if row and check_password_hash(row["password_hash"], password or ""):
        return row
    return None


# ---------- products ----------
def search_products(db, q="", category="", status=""):
    sql = "SELECT * FROM products WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR category LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if category:
        sql += " AND category=?"
        args.append(category)
    if status == "low":
        sql += " AND stock_qty <= reorder_level"
    elif status == "expiring":
        sql += " AND expiry_date IS NOT NULL AND expiry_date <= date('now','+15 days')"
    return db.execute(sql + " ORDER BY name", args).fetchall()


def get_product(db, pid):
    return db.execute("SELECT * FROM products WHERE product_id=?", (pid,)).fetchone()


def save_product(db, data, pid=None):
    cols = ("name", "category", "unit_price", "stock_qty", "reorder_level", "expiry_date", "supplier_id")
    vals = [data[c] for c in cols]
    if pid:
        db.execute("UPDATE products SET name=?,category=?,unit_price=?,stock_qty=?,reorder_level=?,"
                   "expiry_date=?,supplier_id=? WHERE product_id=?", vals + [pid])
    else:
        cur = db.execute("INSERT INTO products(name,category,unit_price,stock_qty,reorder_level,"
                         "expiry_date,supplier_id) VALUES(?,?,?,?,?,?,?)", vals)
        pid = cur.lastrowid
    db.commit()
    return pid


def delete_product(db, pid):
    """Products that already appear on bills cannot be deleted (keeps history intact)."""
    used = db.execute("SELECT COUNT(*) FROM sale_items WHERE product_id=?", (pid,)).fetchone()[0]
    if used:
        raise ValueError("This product appears on past bills, so it cannot be deleted. "
                         "Set its stock to 0 instead.")
    db.execute("DELETE FROM products WHERE product_id=?", (pid,))
    db.commit()


# ---------- billing ----------
def create_bill(db, user_id, items, discount_pct=0, when=None):
    """Create a sale atomically and deduct stock.

    items: list of (product_id, quantity). Raises ValueError with a friendly message.
    """
    if not items:
        raise ValueError("Add at least one item to the bill.")
    if not 0 <= discount_pct <= 100:
        raise ValueError("Discount must be between 0 and 100 percent.")
    merged = {}
    for pid, qty in items:
        if not isinstance(qty, int) or qty <= 0:
            raise ValueError("Quantity must be a positive whole number.")
        merged[pid] = merged.get(pid, 0) + qty

    when = when or datetime.now()
    try:
        db.execute("BEGIN")
        lines, subtotal = [], 0.0
        for pid, qty in merged.items():
            p = get_product(db, pid)
            if p is None:
                raise ValueError("One of the products no longer exists.")
            if p["expiry_date"] and p["expiry_date"] < when.date().isoformat():
                raise ValueError(f"{p['name']} is expired and cannot be sold.")
            if qty > p["stock_qty"]:
                raise ValueError(f"Only {p['stock_qty']} of {p['name']} in stock (requested {qty}).")
            lines.append((pid, qty, p["unit_price"]))
            subtotal += qty * p["unit_price"]
        total = round(subtotal * (1 - discount_pct / 100), 2)
        cur = db.execute("INSERT INTO sales(sale_date,sale_time,user_id,discount_pct,total_amount) "
                         "VALUES(?,?,?,?,?)",
                         (when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S"), user_id, discount_pct, total))
        sid = cur.lastrowid
        for pid, qty, price in lines:
            db.execute("INSERT INTO sale_items(sale_id,product_id,quantity,price) VALUES(?,?,?,?)",
                       (sid, pid, qty, price))
            db.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE product_id=?", (qty, pid))
        db.commit()
        return sid
    except Exception:
        db.rollback()
        raise


def get_bill(db, sale_id):
    sale = db.execute("SELECT s.*, u.username FROM sales s JOIN users u USING(user_id) "
                      "WHERE sale_id=?", (sale_id,)).fetchone()
    if not sale:
        return None, []
    items = db.execute("SELECT p.name, i.quantity, i.price, i.quantity*i.price AS line_total "
                       "FROM sale_items i JOIN products p USING(product_id) WHERE sale_id=?",
                       (sale_id,)).fetchall()
    return sale, items
