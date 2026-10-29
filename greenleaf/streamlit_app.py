
import os
import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from werkzeug.security import check_password_hash

import database
import models
import reports
import seed_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "greenleaf.db")

st.set_page_config(
    page_title="GreenLeaf Grocers",
    page_icon="🥬",
    layout="wide"
)


@st.cache_resource
def initialize_database():
    database.init_db(DB_PATH)

    conn = database.connect(DB_PATH)
    user_count = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]
    conn.close()

    if user_count == 0:
        seed_data.seed(DB_PATH)

    return True


initialize_database()


def get_db():
    return database.connect(DB_PATH)


def login_page():
    st.title("🥬 GreenLeaf Grocers")
    st.subheader("Inventory & Sales Management System")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input(
            "Password", type="password"
        )
        submitted = st.form_submit_button(
            "Login", use_container_width=True
        )

    if submitted:
        conn = get_db()
        try:
            user = models.authenticate(
                conn, username, password
            )

            if user:
                st.session_state["user"] = {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "role": user["role"]
                }
                st.rerun()
            else:
                st.error("Invalid username or password.")
        finally:
            conn.close()

    st.info(
        "Demo Admin: admin / admin123\n\n"
        "Demo Cashier: cashier / cashier123"
    )


def dashboard_page(conn):
    st.title("📊 Dashboard")

    start = (
        date.today() - timedelta(days=29)
    ).isoformat()
    end = date.today().isoformat()

    data = reports.kpis(conn, start, end)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Revenue (30 days)",
        f"₹{data['total_revenue']:,.2f}"
    )
    c2.metric("Total Bills", data["bills"])
    c3.metric(
        "Average Bill",
        f"₹{data['avg_bill_value']:,.2f}"
    )
    c4.metric(
        "Low Stock Products",
        data["low_stock_count"]
    )

    st.subheader("Daily Sales")
    daily = pd.DataFrame(
        reports.daily_sales(conn, start, end)
    )

    if not daily.empty:
        daily["date"] = pd.to_datetime(daily["date"])
        st.line_chart(
            daily.set_index("date")["revenue"]
        )
    else:
        st.info("No sales available for this period.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Low Stock Alerts")
        st.dataframe(
            pd.DataFrame(reports.low_stock(conn)),
            use_container_width=True,
            hide_index=True
        )

    with col2:
        st.subheader("Expiring Products")
        st.dataframe(
            pd.DataFrame(reports.expiring(conn)),
            use_container_width=True,
            hide_index=True
        )


def products_page(conn):
    st.title("📦 Product Inventory")

    search = st.text_input("Search products")

    products = models.search_products(conn, q=search)
    df = pd.DataFrame(
        [dict(p) for p in products]
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    if not df.empty:
        st.download_button(
            "Download Products CSV",
            df.to_csv(index=False).encode("utf-8"),
            "products.csv",
            "text/csv"
        )

    st.subheader("Add New Product")

    categories = [
        "Fruits & Vegetables",
        "Dairy & Eggs",
        "Bakery",
        "Beverages",
        "Snacks",
        "Staples & Grains",
        "Household",
        "Personal Care"
    ]

    with st.form("add_product_form"):
        name = st.text_input("Product Name")
        category = st.selectbox("Category", categories)
        price = st.number_input(
            "Unit Price (₹)", min_value=0.0, step=1.0
        )
        stock = st.number_input(
            "Stock Quantity", min_value=0, step=1
        )
        reorder = st.number_input(
            "Reorder Level", min_value=0, value=10
        )
        has_expiry = st.checkbox("Set expiry date")
        expiry = None

        if has_expiry:
            expiry = st.date_input("Expiry Date")

        save = st.form_submit_button("Save Product")

    if save:
        if not name.strip():
            st.error("Please enter a product name.")
        else:
            try:
                models.save_product(
                    conn,
                    {
                        "name": name.strip(),
                        "category": category,
                        "unit_price": float(price),
                        "stock_qty": int(stock),
                        "reorder_level": int(reorder),
                        "expiry_date": (
                            expiry.isoformat()
                            if expiry else None
                        ),
                        "supplier_id": None
                    }
                )
                st.success("Product added successfully.")
                st.rerun()
            except sqlite3.Error as exc:
                st.error(f"Database error: {exc}")


def billing_page(conn, user):
    st.title("🧾 Billing")

    rows = conn.execute("""
        SELECT product_id, name, unit_price, stock_qty
        FROM products
        WHERE stock_qty > 0
          AND (expiry_date IS NULL
               OR expiry_date >= date('now'))
        ORDER BY name
    """).fetchall()

    products = [dict(row) for row in rows]

    if not products:
        st.warning("No products available for billing.")
        return

    options = {
        f"{p['name']} — ₹{p['unit_price']:.2f} "
        f"(Stock: {p['stock_qty']})": p
        for p in products
    }

    with st.form("billing_form"):
        selected = st.multiselect(
            "Select products", list(options.keys())
        )

        quantities = {}

        for label in selected:
            p = options[label]
            quantities[label] = st.number_input(
                f"Quantity: {p['name']}",
                min_value=1,
                max_value=int(p["stock_qty"]),
                value=1,
                step=1,
                key=f"qty_{p['product_id']}"
            )

        discount = st.number_input(
            "Discount (%)",
            min_value=0.0,
            max_value=100.0,
            step=1.0
        )

        submit = st.form_submit_button("Create Bill")

    if submit:
        items = [
            (options[label]["product_id"], int(qty))
            for label, qty in quantities.items()
        ]

        try:
            sale_id = models.create_bill(
                conn,
                user["user_id"],
                items,
                float(discount)
            )

            sale, lines = models.get_bill(conn, sale_id)

            st.success(f"Bill #{sale_id} created successfully!")
            st.metric(
                "Final Bill Amount",
                f"₹{sale['total_amount']:,.2f}"
            )

            bill_df = pd.DataFrame(
                [dict(line) for line in lines]
            )

            st.dataframe(
                bill_df,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Download Bill CSV",
                bill_df.to_csv(index=False).encode("utf-8"),
                f"bill_{sale_id}.csv",
                "text/csv"
            )

        except (ValueError, sqlite3.Error) as exc:
            st.error(f"Could not create bill: {exc}")


def reports_page(conn):
    st.title("📈 Sales Reports")

    col1, col2 = st.columns(2)

    with col1:
        start = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=29)
        )

    with col2:
        end = st.date_input(
            "End Date",
            value=date.today()
        )

    if start > end:
        st.error("Start date must be before end date.")
        return

    data = reports.full_report(
        conn, start.isoformat(), end.isoformat()
    )

    st.subheader("Sales Summary")

    kpis = data["kpis"]
    a, b, c = st.columns(3)

    a.metric("Revenue", f"₹{kpis['total_revenue']:,.2f}")
    b.metric("Bills", kpis["bills"])
    c.metric("Top Category", kpis["top_category"])

    daily = pd.DataFrame(data["daily"])

    st.subheader("Daily Revenue")

    if not daily.empty:
        daily["date"] = pd.to_datetime(daily["date"])
        st.bar_chart(
            daily.set_index("date")["revenue"]
        )
    else:
        st.info("No sales found for these dates.")

    st.subheader("Top-Selling Products")
    st.dataframe(
        pd.DataFrame(data["top"]),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Category Sales")
    st.dataframe(
        pd.DataFrame(data["categories"]),
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download Daily Sales Report",
        daily.to_csv(index=False).encode("utf-8"),
        "sales_report.csv",
        "text/csv"
    )


def main():
    if "user" not in st.session_state:
        login_page()
        return

    user = st.session_state["user"]

    with st.sidebar:
        st.title("🥬 GreenLeaf")
        st.write(f"User: {user['username']}")
        st.write(f"Role: {user['role']}")

        pages = [
            "Dashboard",
            "Billing"
        ]

        if user["role"] == "admin":
            pages = [
                "Dashboard",
                "Products",
                "Billing",
                "Reports"
            ]

        page = st.radio("Navigation", pages)

        if st.button("Logout"):
            del st.session_state["user"]
            st.rerun()

    conn = get_db()

    try:
        if page == "Dashboard":
            dashboard_page(conn)
        elif page == "Products":
            products_page(conn)
        elif page == "Billing":
            billing_page(conn, user)
        elif page == "Reports":
            reports_page(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
