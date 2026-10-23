"""LAN synchronization service. Windows is the authoritative inventory/store."""
import hmac
import json
import os
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from shopmanager import DATA_DIR, db, now

PORT = 8765
TOKEN_FILE = Path(DATA_DIR) / "pairing_token.txt"
_SERVER = None

def token():
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    return TOKEN_FILE.read_text(encoding="utf-8").strip()

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
    return (f"آدرس سیستم اصلی: http://{local_ip()}:{PORT}\n"
            f"کد اتصال (خصوصی): {token()}\n"
            "گوشی و ویندوز باید در یک شبکه Wi-Fi باشند. این اتصال HTTP فقط برای شبکه محلی مطمئن است.\n"
            "در صورت درخواست فایروال، فقط شبکه خصوصی را مجاز کنید.")

def valid_text(value, maxlen=300):
    return str(value or "").strip()[:maxlen]

def apply_operation(op):
    """Idempotent Android entries. Never give the handset authority over stock."""
    kind = op.get("kind")
    ref = valid_text(op.get("ref"), 100)
    if not ref or len(ref) < 12:
        raise ValueError("شناسه ثبت معتبر نیست")
    with db() as c:
        if kind == "customer":
            row = c.execute("SELECT id FROM customers WHERE client_ref=?", (ref,)).fetchone()
            if row:
                return {"id": row["id"], "duplicate": True}
            name = valid_text(op.get("name"), 150)
            if not name:
                raise ValueError("نام مشتری لازم است")
            cur = c.execute("INSERT INTO customers(name,phone,address,client_ref) VALUES(?,?,?,?)",
                            (name, valid_text(op.get("phone"), 40),
                             valid_text(op.get("address"), 300), ref))
            return {"id": cur.lastrowid, "duplicate": False}
        if kind == "job":
            row = c.execute("SELECT id,order_code FROM jobs WHERE client_ref=?", (ref,)).fetchone()
            if row:
                return {"id": row["id"], "order_code": row["order_code"], "duplicate": True}
            customer_ref = valid_text(op.get("customer_ref"), 100)
            customer = c.execute("SELECT id FROM customers WHERE client_ref=?", (customer_ref,)).fetchone()
            if not customer:
                raise ValueError("ابتدا مشتری مرتبط باید همگام‌سازی شود")
            checks = op.get("checks", [])
            if not isinstance(checks, list) or len(checks) > 40:
                raise ValueError("چک‌لیست معتبر نیست")
            checks = [valid_text(x, 100) for x in checks]
            cur = c.execute("""INSERT INTO jobs(customer_id,client_ref,device,problem,intake_checks,diagnosed_fault,created_at)
                               VALUES(?,?,?,?,?,?,?)""",
                            (customer["id"], ref, valid_text(op.get("device"), 150),
                             valid_text(op.get("reported"), 700),
                             json.dumps(checks, ensure_ascii=False),
                             valid_text(op.get("diagnosis"), 700), now()))
            job_id = cur.lastrowid
            code = f"SM-{now()[:4]}-{job_id:06d}"
            c.execute("UPDATE jobs SET order_code=? WHERE id=?", (code, job_id))
            return {"id": job_id, "order_code": code, "duplicate": False}
        if kind == "consume":
            # Do not queue consumptions offline: master must validate stock live.
            raise ValueError("مصرف موجودی فقط روی سیستم اصلی تأیید می‌شود")
    raise ValueError("نوع ثبت پشتیبانی نمی‌شود")

def snapshot():
    with db() as c:
        customers = [dict(x) for x in c.execute(
            "SELECT id,name,phone,address,client_ref FROM customers ORDER BY id DESC LIMIT 1000")]
        items = [dict(x) for x in c.execute(
            "SELECT id,sku,name,qty,price FROM items ORDER BY id DESC LIMIT 1000")]
        jobs = [dict(x) for x in c.execute(
            """SELECT j.id,j.order_code,j.client_ref,j.device,j.problem,j.intake_checks,
                      j.diagnosed_fault,j.labor,j.discount,j.paid,j.status,j.customer_id,
                      c.name AS customer_name FROM jobs j JOIN customers c ON c.id=j.customer_id
               ORDER BY j.id DESC LIMIT 1000""")]
    return {"role": "master", "customers": customers, "items": items, "jobs": jobs}

class Handler(BaseHTTPRequestHandler):
    def respond(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        supplied = self.headers.get("X-ShopManager-Token", "")
        return hmac.compare_digest(supplied, token())

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"service": "ShopManager", "role": "master"})
            return
        if not self.authorized():
            self.respond(401, {"error": "کد اتصال صحیح نیست"})
            return
        if self.path == "/snapshot":
            self.respond(200, snapshot())
        else:
            self.respond(404, {"error": "not found"})

    def do_POST(self):
        if not self.authorized():
            self.respond(401, {"error": "کد اتصال صحیح نیست"})
            return
        if self.path != "/operation":
            self.respond(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 65536:
                raise ValueError("حجم درخواست نامعتبر است")
            op = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(op, dict):
                raise ValueError("اطلاعات درخواست معتبر نیست")
            self.respond(200, {"ok": True, "result": apply_operation(op)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(400, {"ok": False, "error": str(exc)})
        except Exception:
            self.respond(500, {"ok": False, "error": "خطای داخلی سرور"})

    def log_message(self, fmt, *args):
        pass

def start_server(host="0.0.0.0", port=PORT):
    global _SERVER
    if _SERVER is not None:
        return _SERVER
    token()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="shopmanager-sync", daemon=True).start()
    _SERVER = server
    return server

if __name__ == "__main__":
    from shopmanager import init_db
    init_db()
    print(pairing_info())
    start_server()
    threading.Event().wait()
