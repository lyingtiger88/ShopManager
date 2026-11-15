"""Single-master LAN API for ShopManager.

The master owns the only writable SQLite database. Paired clients authenticate
with revocable device tokens and submit idempotent commands to this process.
"""
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import secrets
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from shopmanager import DATA_DIR, db, now

PORT = 8765
TOKEN_FILE = Path(DATA_DIR) / "pairing_token.txt"
_SERVER = None
_MAX_BODY = 65536


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token():
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def init_sync_schema():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS paired_devices(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, last_seen_at TEXT, revoked INTEGER NOT NULL DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS sync_operations(
            operation_id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
            kind TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS sync_audit(
            id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, action TEXT NOT NULL,
            operation_id TEXT, created_at TEXT NOT NULL
        )""")


BACKUP_DIR = Path(DATA_DIR) / "backups"
BACKUP_KEEP = 30


def create_master_backup():
    """Create a consistent SQLite backup owned by the master, then verify it."""
    init_sync_schema()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = BACKUP_DIR / f"shopmanager-master-{stamp}.sqlite3"
    source_path = Path(__import__("shopmanager").DB_FILE)
    if not source_path.exists():
        raise FileNotFoundError("پایگاه داده اصلی پیدا نشد")
    source = sqlite3.connect(str(source_path), timeout=30)
    target = sqlite3.connect(str(destination), timeout=30)
    try:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError("بررسی سلامت نسخه پشتیبان ناموفق بود: " + str(result))
    except Exception:
        target.close()
        source.close()
        destination.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    backups = sorted(BACKUP_DIR.glob("shopmanager-master-*.sqlite3"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[BACKUP_KEEP:]:
        old.unlink(missing_ok=True)
    return {"path": str(destination), "filename": destination.name,
            "size_bytes": destination.stat().st_size,
            "integrity": "ok", "retained": min(len(backups), BACKUP_KEEP)}


def list_master_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return [{"filename": p.name, "size_bytes": p.stat().st_size,
             "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(BACKUP_DIR.glob("shopmanager-master-*.sqlite3"),
                            key=lambda p: p.stat().st_mtime, reverse=True)]


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "YOUR_PC_IP"
    finally:
        s.close()


def pairing_info():
    init_sync_schema()
    return (f"آدرس سیستم اصلی: http://{local_ip()}:{PORT}\n"
            f"کد جفت‌سازی (خصوصی): {token()}\n"
            "این کد فقط برای افزودن دستگاه جدید است؛ پس از اتصال، برای هر دستگاه کلید مستقل ساخته می‌شود.\n"
            "فقط روی شبکه خصوصی مورد اعتماد استفاده کنید. HTTP برای اینترنت عمومی امن نیست.")


def valid_text(value, maxlen=300):
    return str(value or "").strip()[:maxlen]


def pair_device(pair_code, device_name):
    if not hmac.compare_digest(valid_text(pair_code, 200), token()):
        raise PermissionError("کد جفت‌سازی صحیح نیست")
    name = valid_text(device_name, 80) or "دستگاه جدید"
    device_id = secrets.token_urlsafe(18)
    device_token = secrets.token_urlsafe(36)
    with db() as c:
        c.execute("INSERT INTO paired_devices(id,name,token_hash,created_at) VALUES(?,?,?,?)",
                  (device_id, name, _hash(device_token), now()))
        c.execute("INSERT INTO sync_audit(device_id,action,created_at) VALUES(?,?,?)",
                  (device_id, "paired", now()))
    return {"device_id": device_id, "device_token": device_token, "device_name": name}


def authenticate_device(supplied):
    if not supplied:
        return None
    digest = _hash(supplied)
    with db() as c:
        row = c.execute("""SELECT id,name FROM paired_devices
                           WHERE token_hash=? AND revoked=0""", (digest,)).fetchone()
        if row:
            c.execute("UPDATE paired_devices SET last_seen_at=? WHERE id=?", (now(), row["id"]))
            return dict(row)
    return None


def list_devices():
    init_sync_schema()
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,name,created_at,last_seen_at,revoked FROM paired_devices ORDER BY created_at DESC")]


def revoke_device(device_id):
    with db() as c:
        cur = c.execute("UPDATE paired_devices SET revoked=1 WHERE id=?", (device_id,))
        if not cur.rowcount:
            raise ValueError("دستگاه پیدا نشد")
        c.execute("INSERT INTO sync_audit(device_id,action,created_at) VALUES(?,?,?)",
                  (device_id, "revoked", now()))


def valid_ref(op):
    ref = valid_text(op.get("ref"), 100)
    if len(ref) < 12:
        raise ValueError("شناسه ثبت معتبر نیست")
    return ref


def _existing_operation(c, op_id):
    row = c.execute("SELECT result_json FROM sync_operations WHERE operation_id=?", (op_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def apply_operation(op, device=None):
    """Execute one idempotent command on the master DB only."""
    init_sync_schema()
    device = device or {"id": "local-master", "name": "Master device"}
    if not isinstance(op, dict):
        raise ValueError("اطلاعات درخواست معتبر نیست")
    op_id = valid_text(op.get("operation_id") or op.get("ref"), 100)
    if len(op_id) < 12:
        raise ValueError("شناسه عملیات معتبر نیست")
    kind = valid_text(op.get("kind"), 40)
    with db() as c:
        previous = _existing_operation(c, op_id)
        if previous is not None:
            return {**previous, "duplicate": True}
        result = _apply_in_transaction(c, op, kind)
        c.execute("INSERT INTO sync_operations(operation_id,device_id,kind,result_json,created_at) VALUES(?,?,?,?,?)",
                  (op_id, device["id"], kind, json.dumps(result, ensure_ascii=False), now()))
        c.execute("INSERT INTO sync_audit(device_id,action,operation_id,created_at) VALUES(?,?,?,?)",
                  (device["id"], kind, op_id, now()))
        return result


def _apply_in_transaction(c, op, kind):
    ref = valid_ref(op)
    if kind == "customer":
        row = c.execute("SELECT id FROM customers WHERE client_ref=?", (ref,)).fetchone()
        if row:
            return {"id": row["id"], "duplicate": True}
        first_name = valid_text(op.get("first_name"), 75)
        last_name = valid_text(op.get("last_name"), 75)
        phone = valid_text(op.get("phone"), 40)
        if not first_name or not last_name or not phone:
            legacy_name = valid_text(op.get("name"), 150)
            if not (legacy_name and phone):
                raise ValueError("نام، نام خانوادگی و شماره تماس مشتری الزامی است")
            first_name, last_name = legacy_name, ""
        name = f"{first_name} {last_name}".strip()
        cur = c.execute(
            "INSERT INTO customers(name,first_name,last_name,phone,address,client_ref) VALUES(?,?,?,?,?,?)",
            (name, first_name, last_name, phone, valid_text(op.get("address"), 300), ref))
        return {"id": cur.lastrowid, "duplicate": False}

    if kind == "job":
        row = c.execute("SELECT id,order_code FROM jobs WHERE client_ref=?", (ref,)).fetchone()
        if row:
            return {"id": row["id"], "order_code": row["order_code"], "duplicate": True}
        customer_ref = valid_text(op.get("customer_ref"), 100)
        customer = c.execute("SELECT id FROM customers WHERE client_ref=?", (customer_ref,)).fetchone()
        if not customer and not customer_ref and op.get("customer_id"):
            customer = c.execute("SELECT id FROM customers WHERE id=?", (int(op["customer_id"]),)).fetchone()
        if not customer:
            raise ValueError("ابتدا مشتری مرتبط باید همگام‌سازی شود")
        checks = op.get("checks", [])
        physical = op.get("physical_conditions", [])
        if not isinstance(checks, list) or len(checks) > 40:
            raise ValueError("چک‌لیست معتبر نیست")
        if not isinstance(physical, list) or len(physical) > 40:
            raise ValueError("فهرست وضعیت فیزیکی معتبر نیست")
        checks = [valid_text(x, 100) for x in checks]
        physical = [valid_text(x, 120) for x in physical]
        power_state = valid_text(op.get("power_state"), 10) or "ثبت نشده"
        if power_state not in ("روشن", "خاموش", "ثبت نشده"):
            raise ValueError("وضعیت روشن یا خاموش بودن دستگاه معتبر نیست")
        cur = c.execute("""INSERT INTO jobs(customer_id,client_ref,device,problem,intake_checks,
                           diagnosed_fault,estimate_parts,estimate_labor,power_state,physical_condition,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (customer["id"], ref, valid_text(op.get("device"), 150),
                         valid_text(op.get("reported"), 700), json.dumps(checks, ensure_ascii=False),
                         valid_text(op.get("diagnosis"), 700), max(0, int(op.get("estimate_parts", 0))),
                         max(0, int(op.get("estimate_labor", 0))), power_state,
                         json.dumps(physical, ensure_ascii=False), now()))
        job_id = cur.lastrowid
        code = f"SM-{now()[:4]}-{job_id:06d}"
        c.execute("UPDATE jobs SET order_code=? WHERE id=?", (code, job_id))
        return {"id": job_id, "order_code": code, "duplicate": False}

    if kind == "item":
        sku = valid_text(op.get("sku"), 60)
        name = valid_text(op.get("name"), 150)
        if not name:
            raise ValueError("نام کالا الزامی است")
        qty, cost, price = int(op.get("qty", 0)), int(op.get("cost", 0)), int(op.get("price", 0))
        if min(qty, cost, price) < 0:
            raise ValueError("مقادیر کالا نمی‌توانند منفی باشند")
        if not sku:
            sku = f"ITM-{secrets.token_hex(4).upper()}"
        if c.execute("SELECT 1 FROM items WHERE sku=?", (sku,)).fetchone():
            raise ValueError("کد کالا تکراری است")
        cur = c.execute("INSERT INTO items(sku,name,qty,cost,price) VALUES(?,?,?,?,?)",
                        (sku, name, qty, cost, price))
        return {"id": cur.lastrowid, "sku": sku, "duplicate": False}

    if kind == "stock_receipt":
        item_id, qty = int(op.get("item_id", 0)), int(op.get("qty", 0))
        if item_id <= 0 or qty <= 0:
            raise ValueError("کالا و تعداد ورود باید معتبر باشند")
        item = c.execute("SELECT id FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            raise ValueError("کالا پیدا نشد")
        c.execute("UPDATE items SET qty=qty+? WHERE id=?", (qty, item_id))
        c.execute("INSERT INTO stock_log(item_id,change_qty,reason,created_at) VALUES(?,?,?,?)",
                  (item_id, qty, valid_text(op.get("reason"), 200) or "ورود کالا از دستگاه متصل", now()))
        return {"item_id": item_id, "received": qty, "duplicate": False}

    if kind == "job_payment":
        job_id, paid = int(op.get("job_id", 0)), int(op.get("paid", -1))
        if job_id <= 0 or paid < 0:
            raise ValueError("مبلغ پرداخت معتبر نیست")
        row = c.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("پرونده پیدا نشد")
        c.execute("UPDATE jobs SET paid=? WHERE id=?", (paid, job_id))
        return {"job_id": job_id, "paid": paid, "duplicate": False}

    if kind == "job_status":
        job_id = int(op.get("job_id", 0))
        status = valid_text(op.get("status"), 40)
        if job_id <= 0 or status not in ("در انتظار", "در حال تعمیر", "تکمیل شده", "تحویل شده"):
            raise ValueError("وضعیت پرونده معتبر نیست")
        cur = c.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        if not cur.rowcount:
            raise ValueError("پرونده پیدا نشد")
        return {"job_id": job_id, "status": status, "duplicate": False}

    if kind == "consume":
        raise ValueError("مصرف موجودی فقط با تأیید زنده سیستم اصلی مجاز است")
    raise ValueError("نوع عملیات پشتیبانی نمی‌شود")


def snapshot():
    """Full authoritative read model; no independent subordinate database."""
    with db() as c:
        customers = [dict(x) for x in c.execute(
            "SELECT id,name,first_name,last_name,phone,address,notes,client_ref FROM customers ORDER BY id DESC")]
        items = [dict(x) for x in c.execute(
            "SELECT id,sku,name,qty,cost,price FROM items ORDER BY id DESC")]
        jobs = [dict(x) for x in c.execute(
            """SELECT j.*,c.name AS customer_name,c.first_name,c.last_name,c.phone,c.address
               FROM jobs j JOIN customers c ON c.id=j.customer_id ORDER BY j.id DESC""")]
        stock_log = [dict(x) for x in c.execute(
            """SELECT s.*,i.sku,i.name AS item_name FROM stock_log s
               JOIN items i ON i.id=s.item_id ORDER BY s.id DESC""")]
        job_items = [dict(x) for x in c.execute(
            """SELECT ji.*,i.sku,i.name AS item_name FROM job_items ji
               JOIN items i ON i.id=ji.item_id ORDER BY ji.id DESC""")]
    return {"role": "master", "database_authority": "master",
            "customers": customers, "items": items, "jobs": jobs,
            "stock_log": stock_log, "job_items": job_items,
            "server_time": datetime.now(timezone.utc).isoformat()}


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > _MAX_BODY:
            raise ValueError("حجم درخواست نامعتبر است")
        value = json.loads(self.rfile.read(size).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("ساختار درخواست معتبر نیست")
        return value

    def _device(self):
        return authenticate_device(self.headers.get("X-ShopManager-Token", ""))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.respond(200, {"service": "ShopManager", "role": "master",
                               "database_authority": "master", "pairing_required": True})
            return
        device = self._device()
        if not device:
            self.respond(401, {"error": "دستگاه جفت‌سازی نشده یا دسترسی آن لغو شده است"})
            return
        if path == "/snapshot":
            self.respond(200, snapshot())
        elif path == "/backups":
            self.respond(200, {"backups": list_master_backups()})
        else:
            self.respond(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path == "/pair":
                result = pair_device(payload.get("pairing_code", ""),
                                     payload.get("device_name", "دستگاه جدید"))
                self.respond(200, result)
                return
            device = self._device()
            if not device:
                self.respond(401, {"error": "دستگاه جفت‌سازی نشده یا دسترسی آن لغو شده است"})
                return
            if path == "/operation":
                result = apply_operation(payload, device)
                if payload.get("kind") == "job" and not result.get("duplicate"):
                    try:
                        from shopmanager import export_intake_report
                        export_intake_report(result["id"], open_pdf=False)
                    except Exception:
                        pass
                self.respond(200, {"ok": True, "result": result})
            else:
                self.respond(404, {"error": "not found"})
        except PermissionError as exc:
            self.respond(401, {"ok": False, "error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.respond(400, {"ok": False, "error": str(exc)})
        except Exception:
            self.respond(500, {"ok": False, "error": "خطای داخلی سرور"})

    def log_message(self, fmt, *args):
        pass


def _daily_backup_loop():
    import time
    while True:
        try:
            backups = list_master_backups()
            if not backups:
                create_master_backup()
            else:
                latest = datetime.fromisoformat(backups[0]["modified_at"])
                age = (datetime.now() - latest).total_seconds()
                if age >= 24 * 60 * 60:
                    create_master_backup()
        except Exception:
            # A failed scheduled backup must not terminate the LAN service.
            pass
        time.sleep(60 * 30)


def start_server(host="0.0.0.0", port=PORT):
    global _SERVER
    if _SERVER is not None:
        return _SERVER
    init_sync_schema()
    token()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="shopmanager-sync", daemon=True).start()
    threading.Thread(target=_daily_backup_loop, name="shopmanager-daily-backup", daemon=True).start()
    _SERVER = server
    return server


if __name__ == "__main__":
    from shopmanager import init_db
    init_db()
    print(pairing_info())
    start_server()
    threading.Event().wait()
