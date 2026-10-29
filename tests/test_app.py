"""Unit tests (run with: python -m pytest   or   python -m unittest discover tests).
Each test uses its own temporary SQLite database, never the real one."""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models  # noqa: E402
import reports  # noqa: E402
import utils  # noqa: E402
from app import create_app  # noqa: E402
from database import connect  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"DATABASE": self.path, "TESTING": True, "SECRET_KEY": "t"})
        self.db = connect(self.path)
        models.create_user(self.db, "admin", "pw12345", "admin")
        models.create_user(self.db, "cash", "pw12345", "cashier")
        self.rice = self.add("Rice", 100, 10)
        self.milk = self.add("Milk", 50, 3, reorder=5)

    def tearDown(self):
        self.db.close()
        os.remove(self.path)

    def add(self, name, price, stock, reorder=10, expiry=None):
        data = dict(name=name, category="Staples & Grains", unit_price=price, stock_qty=stock,
                    reorder_level=reorder, expiry_date=expiry, supplier_id=None)
        return models.save_product(self.db, data)

    def stock(self, pid):
        return models.get_product(self.db, pid)["stock_qty"]


class BillingTests(Base):
    def test_bill_total_and_discount(self):
        sid = models.create_bill(self.db, 1, [(self.rice, 2), (self.milk, 1)], discount_pct=10)
        sale, items = models.get_bill(self.db, sid)
        self.assertEqual(sale["total_amount"], 225.0)  # (200+50) * 0.9
        self.assertEqual(len(items), 2)

    def test_stock_deducted_after_sale(self):
        models.create_bill(self.db, 1, [(self.rice, 4)])
        self.assertEqual(self.stock(self.rice), 6)

    def test_cannot_sell_more_than_stock(self):
        with self.assertRaises(ValueError):
            models.create_bill(self.db, 1, [(self.rice, 11)])
        self.assertEqual(self.stock(self.rice), 10)

    def test_duplicate_lines_are_merged_before_stock_check(self):
        with self.assertRaises(ValueError):
            models.create_bill(self.db, 1, [(self.rice, 6), (self.rice, 6)])

    def test_failed_bill_rolls_back_everything(self):
        with self.assertRaises(ValueError):
            models.create_bill(self.db, 1, [(self.rice, 2), (self.milk, 99)])
        self.assertEqual(self.stock(self.rice), 10)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)

    def test_rejects_negative_zero_and_empty(self):
        for items in ([(self.rice, -1)], [(self.rice, 0)], []):
            with self.assertRaises(ValueError):
                models.create_bill(self.db, 1, items)

    def test_rejects_bad_discount_and_expired(self):
        with self.assertRaises(ValueError):
            models.create_bill(self.db, 1, [(self.rice, 1)], discount_pct=120)
        old = self.add("Old yogurt", 20, 5, expiry=(date.today() - timedelta(days=1)).isoformat())
        with self.assertRaises(ValueError):
            models.create_bill(self.db, 1, [(old, 1)])


class ValidationTests(Base):
    def test_product_validation(self):
        _, errs = utils.validate_product({"name": "", "category": "X", "unit_price": "-5",
                                          "stock_qty": "abc", "expiry_date": "2024-13-45"})
        self.assertGreaterEqual(len(errs), 4)

    def test_valid_product(self):
        clean, errs = utils.validate_product({"name": "Tea", "category": "Beverages", "unit_price": "99.5",
                                              "stock_qty": "5", "expiry_date": "2030-01-31"})
        self.assertEqual(errs, [])
        self.assertEqual(clean["unit_price"], 99.5)

    def test_csv_import_skips_bad_rows(self):
        text = "name,category,unit_price,stock_qty\nTea,Beverages,50,10\nBad,Beverages,-1,5\n"
        ok, errors = utils.import_products_csv(self.db, text)
        self.assertEqual(ok, 1)
        self.assertEqual(len(errors), 1)

    def test_cannot_delete_product_with_sales(self):
        models.create_bill(self.db, 1, [(self.rice, 1)])
        with self.assertRaises(ValueError):
            models.delete_product(self.db, self.rice)


class ReportTests(Base):
    def test_kpis_and_alerts(self):
        models.create_bill(self.db, 1, [(self.rice, 2)])
        start = end = date.today().isoformat()
        k = reports.kpis(self.db, start, end)
        self.assertEqual(k["total_revenue"], 200.0)
        self.assertEqual(k["avg_bill_value"], 200.0)
        self.assertEqual(k["low_stock_count"], 2)  # milk (3<=5) and rice (8<=10 after the sale)
        self.assertEqual(reports.top_products(self.db, start, end)[0]["name"], "Rice")


class AuthTests(Base):
    def test_login_hashes_and_authenticates(self):
        row = self.db.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()
        self.assertNotIn("pw12345", row["password_hash"])
        self.assertIsNotNone(models.authenticate(self.db, "admin", "pw12345"))
        self.assertIsNone(models.authenticate(self.db, "admin", "wrong"))

    def test_role_based_access(self):
        c = self.app.test_client()
        self.assertEqual(c.get("/products").status_code, 302)  # not logged in
        c.post("/login", data={"username": "cash", "password": "pw12345"})
        self.assertEqual(c.get("/products").status_code, 302)  # cashier blocked
        self.assertEqual(c.get("/billing").status_code, 200)
        c2 = self.app.test_client()
        c2.post("/login", data={"username": "admin", "password": "pw12345"})
        self.assertEqual(c2.get("/products").status_code, 200)
        self.assertEqual(c2.get("/reports").status_code, 200)

    def test_billing_api_returns_friendly_errors(self):
        c = self.app.test_client()
        c.post("/login", data={"username": "cash", "password": "pw12345"})
        r = c.post("/billing", json={"items": [{"product_id": self.rice, "quantity": 99}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("in stock", r.get_json()["error"])
        r = c.post("/billing", json={"items": [{"product_id": "x", "quantity": "y"}]})
        self.assertEqual(r.status_code, 400)
        r = c.post("/billing", json={"items": [{"product_id": self.rice, "quantity": 1}]})
        self.assertTrue(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
