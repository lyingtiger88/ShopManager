import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shopmanager as app
import sync_server


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


    def test_item_code_is_generated_when_blank(self):
        item_id = app.add_item("", "Charging port", 2, 10, 20)
        with app.db() as c:
            code = c.execute("SELECT sku FROM items WHERE id=?", (item_id,)).fetchone()[0]
        self.assertEqual(code, f"ITM-{item_id:06d}")

    def test_intake_faults_and_estimate_are_saved(self):
        app.save_intake(
            self.job,
            "شارژ نمی‌شود",
            ["شارژ نمی‌شود", "شکستگی نمایشگر"],
            "خرابی سوکت شارژ",
            250000,
            150000,
        )
        row, _, _, _, _ = app.job_summary(self.job)
        self.assertEqual(row["problem"], "شارژ نمی‌شود")
        self.assertEqual(row["diagnosed_fault"], "خرابی سوکت شارژ")
        self.assertEqual(row["estimate_parts"], 250000)
        self.assertEqual(row["estimate_labor"], 150000)
        self.assertIn("شکستگی نمایشگر", row["intake_checks"])


    def test_android_entries_are_idempotent(self):
        customer_ref = "caf35d0e-bf3f-455c-b5a8-2ba7f6e2db7e"
        job_ref = "fc522843-abbb-4f71-afb5-f150d1129a79"
        person = {"kind": "customer", "ref": customer_ref, "name": "Android customer",
                  "phone": "0912", "address": "Street"}
        first = sync_server.apply_operation(person)
        again = sync_server.apply_operation(person)
        self.assertEqual(first["id"], again["id"])
        work = {"kind": "job", "ref": job_ref, "customer_ref": customer_ref,
                "device": "Phone", "reported": "Cannot charge",
                "checks": ["Charging"], "diagnosis": "Port"}
        created = sync_server.apply_operation(work)
        repeat = sync_server.apply_operation(work)
        self.assertEqual(created["order_code"], repeat["order_code"])
        with app.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM jobs WHERE client_ref=?", (job_ref,)).fetchone()[0], 1)

    def test_master_snapshot_includes_records(self):
        records = sync_server.snapshot()
        self.assertEqual(records["role"], "master")
        self.assertTrue(any(item["id"] == self.a for item in records["items"]))

    def test_android_cannot_consume_inventory_without_master_approval(self):
        with self.assertRaises(ValueError):
            sync_server.apply_operation({
                "kind": "consume",
                "ref": "c870e873-692b-4250-82f8-8164e3ccc976",
                "item_id": self.a, "qty": 2})
        with app.db() as c:
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (self.a,)).fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()
