"""Generate demo data: 2 users, suppliers, 55+ products and 700 sales over ~6 months.

Usage:  python seed_data.py            (creates greenleaf.db)
Logins: admin / admin123   cashier / cashier123
"""
import os
import random
import sys
from datetime import date, datetime, timedelta

import database
import models

CATALOG = {
    "Fruits & Vegetables": [("Bananas (1 dozen)", 60), ("Tomatoes 1kg", 40), ("Onions 1kg", 35), ("Potatoes 1kg", 30),
                            ("Apples 1kg", 180), ("Spinach bunch", 20), ("Carrots 500g", 35), ("Mangoes 1kg", 150)],
    "Dairy & Eggs": [("Full Cream Milk 1L", 62), ("Curd 400g", 45), ("Paneer 200g", 90), ("Butter 100g", 58),
                     ("Eggs (tray of 12)", 84), ("Cheese Slices", 130), ("Greek Yogurt", 70)],
    "Bakery": [("Sandwich Bread", 45), ("Multigrain Bread", 55), ("Butter Cookies", 80), ("Croissant", 60),
               ("Fruit Cake Slice", 50), ("Pav Buns", 40), ("Rusk Pack", 65)],
    "Beverages": [("Orange Juice 1L", 110), ("Green Tea 25 bags", 160), ("Filter Coffee 250g", 210),
                  ("Cola 750ml", 40), ("Mineral Water 1L", 20), ("Coconut Water", 45), ("Energy Drink", 125)],
    "Snacks": [("Potato Chips", 30), ("Salted Peanuts", 55), ("Chocolate Bar", 50), ("Instant Noodles", 14),
               ("Granola Bar", 40), ("Namkeen Mix", 75), ("Popcorn Pack", 60)],
    "Staples & Grains": [("Basmati Rice 5kg", 620), ("Wheat Flour 5kg", 260), ("Toor Dal 1kg", 165),
                         ("Sunflower Oil 1L", 145), ("Sugar 1kg", 48), ("Iodised Salt 1kg", 25),
                         ("Chana Dal 1kg", 120), ("Rolled Oats 1kg", 190)],
    "Household": [("Dish Wash Liquid", 99), ("Laundry Detergent 1kg", 210), ("Floor Cleaner 1L", 175),
                  ("Garbage Bags 30pc", 120), ("Paper Towels", 85), ("Toilet Cleaner", 95)],
    "Personal Care": [("Bath Soap 4-pack", 150), ("Shampoo 340ml", 260), ("Toothpaste 150g", 95),
                      ("Hand Wash 250ml", 89), ("Face Wash", 180), ("Deodorant", 220)],
}
PERISHABLE = {"Fruits & Vegetables": 4, "Dairy & Eggs": 8, "Bakery": 5}


def seed(path, seed_value=42, n_sales=720, days=180):
    rnd = random.Random(seed_value)
    if os.path.exists(path):
        os.remove(path)
    database.init_db(path)
    db = database.connect(path)
    models.create_user(db, "admin", "admin123", "admin")
    models.create_user(db, "cashier", "cashier123", "cashier")
    for n, ph in [("Fresh Farms Co.", "9800011111"), ("Daily Dairy Ltd.", "9800022222"),
                  ("Metro Wholesale", "9800033333")]:
        db.execute("INSERT INTO suppliers(name,phone,email) VALUES(?,?,?)",
                   (n, ph, n.split()[0].lower() + "@example.com"))
    today = date.today()
    products = []
    for cat, items in CATALOG.items():
        for name, price in items:
            shelf = PERISHABLE.get(cat)
            expiry = (today + timedelta(days=rnd.randint(2, shelf * 3))).isoformat() if shelf \
                else (today + timedelta(days=rnd.randint(30, 400))).isoformat()
            reorder = rnd.choice([10, 15, 20, 25])
            stock = rnd.randint(reorder + 5, 150)
            cur = db.execute("INSERT INTO products(name,category,unit_price,stock_qty,reorder_level,expiry_date,"
                             "supplier_id) VALUES(?,?,?,?,?,?,?)",
                             (name, cat, price, stock, reorder, expiry, rnd.randint(1, 3)))
            products.append(cur.lastrowid)
    # create demo alert states
    for pid in rnd.sample(products, 8):
        db.execute("UPDATE products SET stock_qty = reorder_level - ? WHERE product_id=?", (rnd.randint(0, 5), pid))
    slow = set(rnd.sample(products, 6))
    for pid in slow:
        db.execute("UPDATE products SET stock_qty = 60 WHERE product_id=?", (pid,))
    weights = {pid: rnd.paretovariate(1.6) for pid in products}
    price = dict(db.execute("SELECT product_id, unit_price FROM products").fetchall())
    for _ in range(n_sales):
        day = today - timedelta(days=int(rnd.triangular(0, days, 0)))
        pool = [p for p in products if not (p in slow and (today - day).days < 30)]
        chosen = set()
        while len(chosen) < rnd.randint(1, 6):
            chosen.add(rnd.choices(pool, [weights[p] for p in pool])[0])
        lines = [(p, rnd.randint(1, 4)) for p in chosen]
        disc = rnd.choice([0, 0, 0, 5, 10])
        total = round(sum(q * price[p] for p, q in lines) * (1 - disc / 100), 2)
        t = datetime.combine(day, datetime.min.time()) + timedelta(minutes=rnd.randint(8 * 60, 21 * 60))
        cur = db.execute("INSERT INTO sales(sale_date,sale_time,user_id,discount_pct,total_amount) VALUES(?,?,?,?,?)",
                         (day.isoformat(), t.strftime("%H:%M:%S"), rnd.choice([1, 2]), disc, total))
        db.executemany("INSERT INTO sale_items(sale_id,product_id,quantity,price) VALUES(?,?,?,?)",
                       [(cur.lastrowid, p, q, price[p]) for p, q in lines])
    db.commit()
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("products", "sales", "sale_items")}
    db.close()
    return counts


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "greenleaf.db")
    print("Seeded:", seed(target), "->", target)
