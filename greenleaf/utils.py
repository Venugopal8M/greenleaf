"""Validation, auth decorators and CSV helpers."""
import csv
import io
from datetime import date, datetime, timedelta
from functools import wraps

from flask import flash, redirect, session, url_for

CATEGORIES = ["Fruits & Vegetables", "Dairy & Eggs", "Bakery", "Beverages",
              "Snacks", "Staples & Grains", "Household", "Personal Care"]


def parse_date(value, field="Date", required=False):
    """Return a 'YYYY-MM-DD' string or None. Raises ValueError on bad input."""
    value = (value or "").strip()
    if not value:
        if required:
            raise ValueError(f"{field} is required.")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError(f"{field} must be a valid date (YYYY-MM-DD).")


def parse_int(value, field, minimum=0):
    try:
        n = int(str(value).strip())
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be a whole number.")
    if n < minimum:
        raise ValueError(f"{field} cannot be less than {minimum}.")
    return n


def parse_float(value, field, minimum=0.0):
    try:
        n = float(str(value).strip())
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be a number.")
    if n != n or n < minimum:
        raise ValueError(f"{field} cannot be less than {minimum:g}.")
    return n


def validate_product(form):
    """Validate a product form/dict. Returns (clean_dict, errors_list)."""
    clean, errors = {}, []

    def run(key, fn):
        try:
            clean[key] = fn()
        except ValueError as exc:
            errors.append(str(exc))

    name = (form.get("name") or "").strip()
    category = (form.get("category") or "").strip()
    if not name:
        errors.append("Product name is required.")
    if not category:
        errors.append("Category is required.")
    clean["name"], clean["category"] = name, category
    run("unit_price", lambda: round(parse_float(form.get("unit_price"), "Unit price"), 2))
    run("stock_qty", lambda: parse_int(form.get("stock_qty"), "Stock quantity"))
    run("reorder_level", lambda: parse_int(form.get("reorder_level") or 10, "Reorder level"))
    run("expiry_date", lambda: parse_date(form.get("expiry_date"), "Expiry date"))
    sid = (form.get("supplier_id") or "").strip()
    clean["supplier_id"] = int(sid) if sid.isdigit() else None
    return clean, errors


def login_required(roles=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("main.login"))
            if roles and session.get("role") not in roles:
                flash("You do not have permission to open that page.", "error")
                return redirect(url_for("main.home"))
            return fn(*a, **kw)
        return wrapper
    return deco


def default_range(days=30):
    end = date.today()
    return (end - timedelta(days=days - 1)).isoformat(), end.isoformat()


def rows_to_csv(rows, columns):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([r[c] for c in columns])
    return buf.getvalue()


def import_products_csv(db, text):
    """Import products from CSV text. Returns (imported_count, error_list).
    Required columns: name, category, unit_price, stock_qty. Bad rows are skipped."""
    reader = csv.DictReader(io.StringIO(text))
    need = {"name", "category", "unit_price", "stock_qty"}
    if not reader.fieldnames or not need.issubset({f.strip().lower() for f in reader.fieldnames}):
        return 0, ["CSV must have the columns: name, category, unit_price, stock_qty "
                   "(optional: reorder_level, expiry_date)."]
    ok, errors = 0, []
    for i, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        clean, errs = validate_product(row)
        if errs:
            errors.append(f"Row {i}: {errs[0]}")
            continue
        db.execute("""INSERT INTO products(name,category,unit_price,stock_qty,reorder_level,expiry_date)
                      VALUES(?,?,?,?,?,?)""",
                   (clean["name"], clean["category"], clean["unit_price"],
                    clean["stock_qty"], clean["reorder_level"], clean["expiry_date"]))
        ok += 1
    db.commit()
    return ok, errors
