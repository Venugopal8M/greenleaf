"""All web routes (one blueprint)."""
from flask import (Blueprint, Response, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import models
import reports
from database import get_db
from utils import (CATEGORIES, default_range, import_products_csv, login_required,
                   parse_date, rows_to_csv, validate_product)

bp = Blueprint("main", __name__)


def _range():
    d_start, d_end = default_range(30)
    try:
        start = parse_date(request.args.get("start"), "Start date") or d_start
        end = parse_date(request.args.get("end"), "End date") or d_end
    except ValueError as exc:
        flash(str(exc), "error")
        return d_start, d_end
    if start > end:
        flash("Start date must be before the end date.", "error")
        return d_start, d_end
    return start, end


# ---------- auth ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = models.authenticate(get_db(), request.form.get("username"), request.form.get("password"))
        if user:
            session.clear()
            session.update(user_id=user["user_id"], username=user["username"], role=user["role"])
            return redirect(url_for("main.home"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/")
@login_required()
def home():
    if session["role"] == "cashier":
        return redirect(url_for("main.billing"))
    start, end = default_range(30)
    data = reports.full_report(get_db(), start, end)
    return render_template("dashboard.html", k=data["kpis"], low=data["low_stock"][:6],
                           exp=data["expiring"][:6], start=start, end=end)


# ---------- products ----------
@bp.route("/products")
@login_required(["admin"])
def products():
    q, cat, status = (request.args.get(k, "").strip() for k in ("q", "category", "status"))
    rows = models.search_products(get_db(), q, cat, status)
    return render_template("products.html", rows=rows, q=q, cat=cat, status=status, categories=CATEGORIES)


def _form(pid=None):
    db = get_db()
    suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    product = models.get_product(db, pid) if pid else None
    if pid and not product:
        flash("Product not found.", "error")
        return redirect(url_for("main.products"))
    values = dict(product) if product else {"reorder_level": 10}
    if request.method == "POST":
        values = request.form.to_dict()
        clean, errors = validate_product(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            models.save_product(db, clean, pid)
            flash("Product saved.", "ok")
            return redirect(url_for("main.products"))
    return render_template("product_form.html", p=values, pid=pid, categories=CATEGORIES, suppliers=suppliers)


@bp.route("/products/add", methods=["GET", "POST"])
@login_required(["admin"])
def product_add():
    return _form()


@bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required(["admin"])
def product_edit(pid):
    return _form(pid)


@bp.route("/products/<int:pid>/delete", methods=["POST"])
@login_required(["admin"])
def product_delete(pid):
    try:
        models.delete_product(get_db(), pid)
        flash("Product deleted.", "ok")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.products"))


@bp.route("/products/import", methods=["POST"])
@login_required(["admin"])
def products_import():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Choose a .csv file to import.", "error")
        return redirect(url_for("main.products"))
    try:
        text = f.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("The file could not be read. Save it as UTF-8 CSV and try again.", "error")
        return redirect(url_for("main.products"))
    ok, errors = import_products_csv(get_db(), text)
    flash(f"Imported {ok} products.", "ok" if ok else "error")
    for e in errors[:5]:
        flash(e, "error")
    return redirect(url_for("main.products"))


@bp.route("/products/export")
@login_required(["admin"])
def products_export():
    rows = models.search_products(get_db())
    cols = ["product_id", "name", "category", "unit_price", "stock_qty", "reorder_level", "expiry_date"]
    return _csv(rows_to_csv(rows, cols), "products.csv")


def _csv(text, name):
    return Response(text, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


# ---------- billing ----------
@bp.route("/billing", methods=["GET", "POST"])
@login_required(["admin", "cashier"])
def billing():
    db = get_db()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            items = [(int(i["product_id"]), i["quantity"]) for i in data.get("items", [])]
            discount = float(data.get("discount", 0) or 0)
            sid = models.create_bill(db, session["user_id"], items, discount)
            return jsonify(ok=True, url=url_for("main.bill", sale_id=sid))
        except (ValueError, KeyError, TypeError) as exc:
            msg = str(exc) if isinstance(exc, ValueError) and not str(exc).startswith("invalid literal") \
                else "Check the items and quantities and try again."
            return jsonify(ok=False, error=msg), 400
    prods = db.execute("SELECT product_id,name,category,unit_price,stock_qty FROM products "
                       "WHERE stock_qty>0 AND (expiry_date IS NULL OR expiry_date>=date('now')) "
                       "ORDER BY name").fetchall()
    return render_template("billing.html", products=[dict(p) for p in prods])


@bp.route("/bill/<int:sale_id>")
@login_required(["admin", "cashier"])
def bill(sale_id):
    sale, items = models.get_bill(get_db(), sale_id)
    if not sale:
        flash("Bill not found.", "error")
        return redirect(url_for("main.home"))
    return render_template("bill.html", sale=sale, items=items)


@bp.route("/bill/<int:sale_id>/csv")
@login_required(["admin", "cashier"])
def bill_csv(sale_id):
    sale, items = models.get_bill(get_db(), sale_id)
    if not sale:
        return redirect(url_for("main.home"))
    body = rows_to_csv(items, ["name", "quantity", "price", "line_total"])
    body += f"Discount %,{sale['discount_pct']}\nTotal,{sale['total_amount']}\n"
    return _csv(body, f"bill_{sale_id}.csv")


# ---------- reports ----------
@bp.route("/reports")
@login_required(["admin"])
def reports_page():
    start, end = _range()
    return render_template("reports.html", start=start, end=end)


@bp.route("/api/reports")
@login_required(["admin"])
def reports_api():
    start, end = _range()
    return jsonify(reports.full_report(get_db(), start, end))


@bp.route("/reports/export/<name>.csv")
@login_required(["admin"])
def reports_export(name):
    start, end = _range()
    db = get_db()
    sources = {
        "daily": (lambda: reports.daily_sales(db, start, end), ["date", "revenue", "bills"]),
        "monthly": (lambda: reports.monthly_sales(db, start, end), ["month", "revenue", "bills"]),
        "top": (lambda: reports.top_products(db, start, end), ["name", "quantity", "revenue"]),
        "low_stock": (lambda: reports.low_stock(db), ["name", "category", "stock_qty", "reorder_level"]),
        "expiry": (lambda: reports.expiring(db), ["name", "category", "stock_qty", "expiry_date"]),
    }
    if name not in sources:
        flash("Unknown report.", "error")
        return redirect(url_for("main.reports_page"))
    fn, cols = sources[name]
    return _csv(rows_to_csv(fn(), cols), f"{name}_report.csv")
