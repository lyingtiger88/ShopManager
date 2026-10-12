import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shopmanager as app


class InventoryCartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name) / "shopmanager.sqlite3"
        self.patch = patch.object(app, "DB_FILE", self.database)
        self.patch.start()
        app.init_db()
        customer = app.add_customer("Test customer")
        self.job = app.create_job(customer, "Device", "Repair")
        self.a = app.add_item("A", "Screen", 5, 30, 60)
        self.b = app.add_item("B", "Battery", 4, 10, 25)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_multiple_items_and_quantities(self):
        app.use_items(self.job, [(self.a, 2), (self.b, 3)])
        with app.db() as c:
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (self.a,)).fetchone()[0], 3)
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (self.b,)).fetchone()[0], 1)
        row, lines, parts, costs, total = app.job_summary(self.job)
        self.assertEqual(len(lines), 2)
        self.assertEqual((parts, costs, total), (195, 90, 195))

    def test_insufficient_stock_rolls_back_all(self):
        with self.assertRaises(ValueError):
            app.use_items(self.job, [(self.a, 2), (self.b, 99)])
        with app.db() as c:
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (self.a,)).fetchone()[0], 5)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM job_items").fetchone()[0], 0)

    def test_duplicate_item_ids_are_combined(self):
        app.use_items(self.job, [(self.a, 2), (self.a, 2)])
        with app.db() as c:
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (self.a,)).fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT qty FROM job_items").fetchone()[0], 4)

    def test_order_code_stays_unique_and_migration(self):
        other = app.create_job(app.add_customer("Another"), "Other", "Work")
        with app.db() as c:
            a = c.execute("SELECT order_code FROM jobs WHERE id=?", (self.job,)).fetchone()[0]
            b = c.execute("SELECT order_code FROM jobs WHERE id=?", (other,)).fetchone()[0]
        self.assertNotEqual(a, b)
        app.init_db()
        with app.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(DISTINCT order_code) FROM jobs").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
