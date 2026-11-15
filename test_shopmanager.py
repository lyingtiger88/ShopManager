import sqlite3
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
            "خاموش",
            ["شکستگی قاب", "باتری مفقود"],
        )
        row, _, _, _, _ = app.job_summary(self.job)
        self.assertEqual(row["problem"], "شارژ نمی‌شود")
        self.assertEqual(row["diagnosed_fault"], "خرابی سوکت شارژ")
        self.assertEqual(row["estimate_parts"], 250000)
        self.assertEqual(row["estimate_labor"], 150000)
        self.assertIn("شکستگی نمایشگر", row["intake_checks"])
        self.assertEqual(row["power_state"], "خاموش")
        self.assertIn("باتری مفقود", row["physical_condition"])


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

class MasterClientArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name) / "master.sqlite3"
        self.p_db = patch.object(app, "DB_FILE", self.database)
        self.p_db.start()
        self.p_token = patch.object(sync_server, "TOKEN_FILE", Path(self.tmp.name) / "pairing.txt")
        self.p_token.start()
        app.init_db()
        sync_server.init_sync_schema()
        self.master_code = sync_server.token()

    def tearDown(self):
        self.p_token.stop()
        self.p_db.stop()
        self.tmp.cleanup()

    def test_pairing_issues_unique_device_credentials(self):
        first = sync_server.pair_device(self.master_code, "صندوق")
        second = sync_server.pair_device(self.master_code, "انبار")
        self.assertNotEqual(first["device_token"], second["device_token"])
        self.assertNotEqual(first["device_id"], second["device_id"])
        self.assertEqual(sync_server.authenticate_device(first["device_token"])["id"], first["device_id"])
        self.assertEqual(len(sync_server.list_devices()), 2)

    def test_invalid_pairing_code_is_rejected(self):
        with self.assertRaises(PermissionError):
            sync_server.pair_device("wrong-code", "unknown")

    def test_revoked_device_cannot_authenticate(self):
        paired = sync_server.pair_device(self.master_code, "گوشی")
        sync_server.revoke_device(paired["device_id"])
        self.assertIsNone(sync_server.authenticate_device(paired["device_token"]))

    def test_all_subordinate_operations_write_to_one_master_database(self):
        device = sync_server.pair_device(self.master_code, "گوشی")
        client = sync_server.authenticate_device(device["device_token"])
        customer_ref = "8a87c0d3-5f22-4ef3-bd9a-91b2f33aab22"
        customer = sync_server.apply_operation({
            "operation_id": customer_ref, "kind": "customer", "ref": customer_ref,
            "first_name": "Test", "last_name": "Customer", "phone": "09120000000"
        }, client)
        item_ref = "bf57d2f4-c8de-46d7-8e6b-8efadccab333"
        item = sync_server.apply_operation({
            "operation_id": item_ref, "kind": "item", "ref": item_ref,
            "sku": "MASTER-01", "name": "کالای مرکزی", "qty": 2, "cost": 10, "price": 20
        }, client)
        receipt_ref = "5a22e1c0-73d3-43c1-9f6b-94bfe6d2ce13"
        receipt = sync_server.apply_operation({
            "operation_id": receipt_ref, "kind": "stock_receipt", "ref": receipt_ref,
            "item_id": item["id"], "qty": 3
        }, client)
        self.assertEqual(receipt["received"], 3)
        with app.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (item["id"],)).fetchone()[0], 5)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM stock_log").fetchone()[0], 1)

    def test_retry_is_idempotent_and_does_not_double_receive_stock(self):
        device = sync_server.pair_device(self.master_code, "گوشی")
        client = sync_server.authenticate_device(device["device_token"])
        with app.db() as c:
            item_id = c.execute("INSERT INTO items(sku,name,qty,cost,price) VALUES(?,?,?,?,?)",
                                ("R-1", "Test", 4, 1, 2)).lastrowid
        op = {"operation_id": "a5a8f5d3-9c7f-4f80-9c4a-0c6b6fdd1e15",
              "ref": "a5a8f5d3-9c7f-4f80-9c4a-0c6b6fdd1e15",
              "kind": "stock_receipt", "item_id": item_id, "qty": 2}
        first = sync_server.apply_operation(op, client)
        second = sync_server.apply_operation(op, client)
        self.assertFalse(first.get("duplicate", False))
        self.assertTrue(second["duplicate"])
        with app.db() as c:
            self.assertEqual(c.execute("SELECT qty FROM items WHERE id=?", (item_id,)).fetchone()[0], 6)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM stock_log").fetchone()[0], 1)

    def test_snapshot_contains_complete_master_read_models(self):
        app.add_item("SNAP-1", "Snapshot item", 3, 4, 5)
        result = sync_server.snapshot()
        self.assertEqual(result["database_authority"], "master")
        self.assertIn("stock_log", result)
        self.assertIn("job_items", result)
        self.assertEqual(len(result["items"]), 1)



class MasterBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name) / "master.sqlite3"
        self.backups = Path(self.tmp.name) / "backups"
        self.p_db = patch.object(app, "DB_FILE", self.database)
        self.p_db.start()
        self.p_dir = patch.object(sync_server, "BACKUP_DIR", self.backups)
        self.p_dir.start()
        app.init_db()
        app.add_item("BACKUP-1", "Backup test item", 7, 12, 20)

    def tearDown(self):
        self.p_dir.stop()
        self.p_db.stop()
        self.tmp.cleanup()

    def test_backup_is_created_and_integrity_verified(self):
        result = sync_server.create_master_backup()
        backup = Path(result["path"])
        self.assertTrue(backup.exists())
        self.assertEqual(result["integrity"], "ok")
        restored = sqlite3.connect(str(backup))
        try:
            self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(restored.execute("SELECT qty FROM items WHERE sku='BACKUP-1'").fetchone()[0], 7)
        finally:
            restored.close()

    def test_backup_listing_is_newest_first(self):
        first = sync_server.create_master_backup()
        second = sync_server.create_master_backup()
        listed = sync_server.list_master_backups()
        self.assertGreaterEqual(len(listed), 1)
        self.assertEqual(listed[0]["filename"], second["filename"])

    def test_backup_retention_removes_oldest_after_limit(self):
        for i in range(sync_server.BACKUP_KEEP + 2):
            sync_server.create_master_backup()
        self.assertLessEqual(len(sync_server.list_master_backups()), sync_server.BACKUP_KEEP)



    def test_restore_replaces_master_database_and_creates_safety_backup(self):
        app.add_item("RESTORE-OLD", "Old live data", 1, 2, 3)
        backup = sync_server.create_master_backup()
        app.add_item("RESTORE-NEW", "New live data", 9, 8, 7)
        result = sync_server.restore_master_backup(backup["filename"])
        self.assertEqual(result["integrity"], "ok")
        self.assertTrue(result["safety_backup"].startswith("shopmanager-master-"))
        with app.db() as c:
            skus = {row[0] for row in c.execute("SELECT sku FROM items")}
        self.assertIn("RESTORE-OLD", skus)
        self.assertNotIn("RESTORE-NEW", skus)

    def test_restore_rejects_path_traversal_and_unknown_files(self):
        with self.assertRaises(ValueError):
            sync_server.restore_master_backup("../outside.sqlite3")
        with self.assertRaises(FileNotFoundError):
            sync_server.restore_master_backup("shopmanager-master-not-found.sqlite3")



    def test_restore_rejects_corrupt_database_file(self):
        corrupt = self.backups / "shopmanager-master-corrupt.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        with self.assertRaises(sqlite3.DatabaseError):
            sync_server.restore_master_backup(corrupt.name)

