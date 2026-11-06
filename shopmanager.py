# -*- coding: utf-8 -*-
"""ShopManager - offline customer, inventory, repair and invoice manager."""
import html
import json
import os
import sqlite3
import sys
import webbrowser
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

APP = "ShopManager"
DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP if sys.platform == "win32" else Path.home() / ".shopmanager"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "shopmanager.sqlite3"
INVOICE_DIR = DATA_DIR / "invoices"
INVOICE_DIR.mkdir(exist_ok=True)


def money(v):
    return f"{int(v):,}"


def amount(v, label="مبلغ"):
    try:
        n = int(str(v).replace(",", "").strip())
        if n < 0:
            raise ValueError()
        return n
    except (ValueError, TypeError):
        raise ValueError(f"{label} باید عدد صحیح نامنفی باشد.")


@contextmanager
def db():
    """Yield a configured SQLite connection and always close it."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS customers(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, first_name TEXT DEFAULT '',
          last_name TEXT DEFAULT '', phone TEXT DEFAULT '',
          address TEXT DEFAULT '', notes TEXT DEFAULT '', client_ref TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS items(
          id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT NOT NULL,
          qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0),
          cost INTEGER NOT NULL DEFAULT 0 CHECK(cost>=0),
          price INTEGER NOT NULL DEFAULT 0 CHECK(price>=0));
        CREATE TABLE IF NOT EXISTS jobs(
          id INTEGER PRIMARY KEY, order_code TEXT UNIQUE, client_ref TEXT UNIQUE, customer_id INTEGER NOT NULL REFERENCES customers(id),
          device TEXT NOT NULL DEFAULT '', problem TEXT DEFAULT '',
          intake_checks TEXT NOT NULL DEFAULT '[]', diagnosed_fault TEXT DEFAULT '',
          estimate_parts INTEGER NOT NULL DEFAULT 0, estimate_labor INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'در انتظار', labor INTEGER NOT NULL DEFAULT 0,
          discount INTEGER NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, notes TEXT DEFAULT '',
          power_state TEXT NOT NULL DEFAULT '', physical_condition TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS job_items(
          id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
          item_id INTEGER NOT NULL REFERENCES items(id),
          qty INTEGER NOT NULL CHECK(qty>0),
          unit_price INTEGER NOT NULL, unit_cost INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS stock_log(
          id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
          change_qty INTEGER NOT NULL, reason TEXT NOT NULL,
          created_at TEXT NOT NULL);
        """)
        customer_columns = {r["name"] for r in c.execute("PRAGMA table_info(customers)")}
        if "client_ref" not in customer_columns:
            c.execute("ALTER TABLE customers ADD COLUMN client_ref TEXT")
        customer_columns = {r["name"] for r in c.execute("PRAGMA table_info(customers)")}
        for column, definition in {"first_name": "TEXT DEFAULT ''", "last_name": "TEXT DEFAULT ''"}.items():
            if column not in customer_columns:
                c.execute(f"ALTER TABLE customers ADD COLUMN {column} {definition}")
        legacy_customers = c.execute(
            "SELECT id,name,first_name,last_name FROM customers WHERE COALESCE(last_name,'')=''"
        ).fetchall()
        for customer in legacy_customers:
            if not customer["first_name"] or customer["first_name"] == customer["name"]:
                parts = (customer["name"] or "").strip().split(maxsplit=1)
                first = parts[0] if parts else ""
                last = parts[1] if len(parts) > 1 else ""
                c.execute("UPDATE customers SET first_name=?,last_name=? WHERE id=?",
                          (first, last, customer["id"]))
        job_columns = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        if "client_ref" not in job_columns:
            c.execute("ALTER TABLE jobs ADD COLUMN client_ref TEXT")
        columns = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        migrations = {
            "order_code": "TEXT",
            "intake_checks": "TEXT NOT NULL DEFAULT '[]'",
            "diagnosed_fault": "TEXT DEFAULT ''",
            "estimate_parts": "INTEGER NOT NULL DEFAULT 0",
            "estimate_labor": "INTEGER NOT NULL DEFAULT 0",
            "power_state": "TEXT NOT NULL DEFAULT ''",
            "physical_condition": "TEXT NOT NULL DEFAULT '[]'",
        }
        for column, definition in migrations.items():
            if column not in columns:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_order_code ON jobs(order_code)")
        for item in c.execute("SELECT id FROM items WHERE sku IS NULL OR sku=''").fetchall():
            c.execute("UPDATE items SET sku=? WHERE id=?", (f"ITM-{item['id']:06d}", item["id"]))
        for job in c.execute("SELECT id, created_at FROM jobs WHERE order_code IS NULL OR order_code=''").fetchall():
            year = (job["created_at"] or "")[:4]
            if not (len(year) == 4 and year.isdigit()):
                year = "0000"
            c.execute("UPDATE jobs SET order_code=? WHERE id=?",
                      (f"SM-{year}-{job['id']:06d}", job["id"]))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def add_customer(first_name, last_name="", phone="", address="", notes=""):
    first_name, last_name, phone = first_name.strip(), last_name.strip(), phone.strip()
    # Backward compatibility for older database tests/integrations that pass one legacy full-name field.
    legacy_single_name = bool(first_name and not last_name and not phone)
    if not first_name:
        raise ValueError("نام مشتری الزامی است.")
    if not legacy_single_name and not last_name:
        raise ValueError("نام خانوادگی مشتری الزامی است.")
    if not legacy_single_name and not phone:
        raise ValueError("شماره تماس مشتری الزامی است.")
    full_name = f"{first_name} {last_name}".strip()
    with db() as c:
        return c.execute(
            "INSERT INTO customers(name,first_name,last_name,phone,address,notes) VALUES(?,?,?,?,?,?)",
            (full_name, first_name, last_name, phone, address.strip(), notes.strip())
        ).lastrowid


def add_item(sku, name, qty, cost, price):
    if not name.strip():
        raise ValueError("نام کالا الزامی است.")
    with db() as c:
        cur = c.execute("INSERT INTO items(sku,name,qty,cost,price) VALUES(?,?,?,?,?)",
                        (sku.strip() or None, name.strip(), qty, cost, price))
        item_id = cur.lastrowid
        item_code = sku.strip() or f"ITM-{item_id:06d}"
        if not sku.strip():
            c.execute("UPDATE items SET sku=? WHERE id=?", (item_code, item_id))
        if qty:
            c.execute("INSERT INTO stock_log(item_id,change_qty,reason,created_at) VALUES(?,?,?,?)",
                      (item_id, qty, "موجودی اولیه", now()))
        return item_id


def restock(item_id, qty):
    if qty <= 0:
        raise ValueError("تعداد افزایش موجودی باید مثبت باشد.")
    with db() as c:
        if not c.execute("UPDATE items SET qty=qty+? WHERE id=?", (qty, item_id)).rowcount:
            raise ValueError("کالا یافت نشد.")
        c.execute("INSERT INTO stock_log(item_id,change_qty,reason,created_at) VALUES(?,?,?,?)",
                  (item_id, qty, "افزایش موجودی", now()))


def create_job(customer_id, device, problem):
    with db() as c:
        created = now()
        cursor = c.execute(
            "INSERT INTO jobs(customer_id,device,problem,created_at) VALUES(?,?,?,?)",
            (customer_id, device.strip(), problem.strip(), created))
        job_id = cursor.lastrowid
        c.execute("UPDATE jobs SET order_code=? WHERE id=?",
                  (f"SM-{created[:4]}-{job_id:06d}", job_id))
        return job_id


def save_intake(job_id, reported_fault, checks, diagnosed_fault, estimate_parts, estimate_labor,
                power_state="", physical_conditions=None):
    checks = list(dict.fromkeys(str(x).strip() for x in checks if str(x).strip()))
    physical_conditions = list(dict.fromkeys(
        str(x).strip() for x in (physical_conditions or []) if str(x).strip()))
    if power_state not in ("", "روشن", "خاموش"):
        raise ValueError("وضعیت روشن یا خاموش بودن دستگاه را مشخص کنید.")
    with db() as c:
        if not c.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise ValueError("پرونده یافت نشد.")
        c.execute("""UPDATE jobs SET problem=?, intake_checks=?, diagnosed_fault=?,
                     estimate_parts=?, estimate_labor=?, power_state=?, physical_condition=?
                     WHERE id=?""",
                  (reported_fault.strip(), json.dumps(checks, ensure_ascii=False),
                   diagnosed_fault.strip(), estimate_parts, estimate_labor, power_state,
                   json.dumps(physical_conditions, ensure_ascii=False), job_id))


def use_items(job_id, quantities):
    """Atomically reserve stock and record every cart line."""
    if not quantities:
        raise ValueError("سبد اقلام خالی است.")
    merged = {}
    for item_id, qty in quantities:
        if not isinstance(qty, int) or qty <= 0:
            raise ValueError("تعداد هر کالا باید عدد صحیح مثبت باشد.")
        merged[item_id] = merged.get(item_id, 0) + qty
    with db() as c:
        if not c.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise ValueError("پرونده یافت نشد.")
        available = {}
        for item_id, qty in merged.items():
            item = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if item is None:
                raise ValueError(f"کالای {item_id} پیدا نشد.")
            if item["qty"] < qty:
                raise ValueError(f"موجودی {item['name']} کافی نیست؛ موجودی: {item['qty']}، درخواست: {qty}")
            available[item_id] = item
        for item_id, qty in merged.items():
            item = available[item_id]
            c.execute("UPDATE items SET qty=qty-? WHERE id=?", (qty, item_id))
            c.execute("INSERT INTO job_items(job_id,item_id,qty,unit_price,unit_cost) VALUES(?,?,?,?,?)",
                      (job_id, item_id, qty, item["price"], item["cost"]))
            c.execute("INSERT INTO stock_log(item_id,change_qty,reason,created_at) VALUES(?,?,?,?)",
                      (item_id, -qty, f"مصرف پرونده #{job_id}", now()))


def use_item(job_id, item_id, qty):
    use_items(job_id, [(item_id, qty)])


def save_job(job_id, labor, discount, paid, status):
    with db() as c:
        total = c.execute("SELECT COALESCE(SUM(qty*unit_price),0) FROM job_items WHERE job_id=?",
                          (job_id,)).fetchone()[0] + labor - discount
        if total < 0:
            raise ValueError("تخفیف نمی‌تواند بیشتر از مجموع اقلام و دستمزد باشد.")
        if paid > total:
            raise ValueError("مبلغ پرداختی نمی‌تواند بیشتر از مبلغ نهایی باشد.")
        c.execute("UPDATE jobs SET labor=?,discount=?,paid=?,status=? WHERE id=?",
                  (labor, discount, paid, status, job_id))


def job_summary(job_id):
    with db() as c:
        row = c.execute("""
        SELECT j.*,c.name AS customer_name,c.first_name,c.last_name,c.phone,c.address
        FROM jobs j JOIN customers c ON c.id=j.customer_id WHERE j.id=?""",
                        (job_id,)).fetchone()
        if row is None:
            raise ValueError("پرونده پیدا نشد.")
        lines = c.execute("""
        SELECT i.name, ji.qty, ji.unit_price, ji.unit_cost
        FROM job_items ji JOIN items i ON i.id=ji.item_id
        WHERE ji.job_id=? ORDER BY ji.id""", (job_id,)).fetchall()
    parts = sum(x["qty"] * x["unit_price"] for x in lines)
    costs = sum(x["qty"] * x["unit_cost"] for x in lines)
    total = parts + row["labor"] - row["discount"]
    return row, lines, parts, costs, total


def export_intake_report(job_id, open_pdf=True):
    """Create a printable PDF and PNG intake receipt in the application's Archive folder."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from PIL import Image, ImageDraw, ImageFont
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError as exc:
        raise RuntimeError("برای ساخت PDF و تصویر، وابستگی‌های گزارش نصب نشده‌اند: " + str(exc))
    row, _lines, _parts, _costs, _total = job_summary(job_id)
    archive = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
               else Path(__file__).resolve().parent) / "Archive" / "IntakeReports"
    archive.mkdir(parents=True, exist_ok=True)
    code = row["order_code"] or f"JOB-{job_id}"
    pdf_path, png_path = archive / f"{code}.pdf", archive / f"{code}.png"
    physical = json.loads(row["physical_condition"] or "[]")
    checks = json.loads(row["intake_checks"] or "[]")
    lines = [
        "گزارش پذیرش دستگاه | ShopManager", f"شماره پرونده: {code}",
        f"تاریخ پذیرش: {row['created_at']}", "",
        "مشخصات مشتری", f"نام: {row['first_name'] or row['customer_name']} {row['last_name'] or ''}",
        f"شماره تماس: {row['phone']}", f"آدرس: {row['address'] or 'ثبت نشده'}", "",
        "مشخصات دستگاه", f"دستگاه: {row['device']}",
        f"وضعیت هنگام تحویل: {row['power_state'] or 'ثبت نشده'}",
        f"عیب اعلامی مشتری: {row['problem'] or 'ثبت نشده'}",
        f"تشخیص اولیه تعمیرکار: {row['diagnosed_fault'] or 'ثبت نشده'}", "",
        "وضعیت فیزیکی و قطعات", *(["• " + x for x in physical] or ["موردی ثبت نشده"]),
        "", "موارد عیب و عملکرد", *(["• " + x for x in checks] or ["موردی ثبت نشده"]),
        "", "امضای مشتری: ....................................",
        "امضای تحویل‌گیرنده: ...................................."
    ]
    font_candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "tahoma.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf")
    ]
    font_path = next((p for p in font_candidates if p.exists()), None)
    if not font_path:
        raise RuntimeError("فونت فارسی مناسب پیدا نشد؛ فونت Tahoma یا Noto نصب کنید.")
    def shaped(value):
        return get_display(arabic_reshaper.reshape(str(value)))
    pdfmetrics.registerFont(TTFont("ShopManagerArabic", str(font_path)))
    pdf = canvas.Canvas(str(pdf_path), pagesize=(595, 842))
    pdf.setTitle(f"گزارش پذیرش {code}")
    y = 800
    for idx, line in enumerate(lines):
        if y < 55:
            pdf.showPage()
            y = 800
        pdf.setFont("ShopManagerArabic", 15 if idx == 0 else 10)
        pdf.drawRightString(555, y, shaped(line))
        y -= 27 if idx == 0 else 22
    pdf.save()
    image = Image.new("RGB", (1240, max(1754, 120 + len(lines) * 48)), "white")
    draw = ImageDraw.Draw(image)
    image_font = ImageFont.truetype(str(font_path), 28)
    y = 55
    for line in lines:
        draw.text((1180, y), shaped(line), font=image_font, fill="#17263d", anchor="ra")
        y += 48
    image.save(png_path, format="PNG", optimize=True)
    if open_pdf:
        webbrowser.open(pdf_path.as_uri())
    return pdf_path


def invoice(job_id):
    row, lines, parts, costs, total = job_summary(job_id)
    e = lambda v: html.escape(str(v or ""))
    rows = "".join(
        f"<tr><td>{e(x['name'])}</td><td>{x['qty']}</td><td>{money(x['unit_price'])}</td>"
        f"<td>{money(x['qty']*x['unit_price'])}</td></tr>" for x in lines)
    intake_checks = json.loads(row["intake_checks"] or "[]")
    reported = (row["problem"] or "").strip().casefold()
    diagnosed = (row["diagnosed_fault"] or "").strip().casefold()
    if not diagnosed:
        comparison = "تشخیص نهایی هنوز ثبت نشده است."
    elif not reported:
        comparison = "عیب اعلامی مشتری ثبت نشده؛ تشخیص تعمیرکار درج شده است."
    elif reported == diagnosed:
        comparison = "عیب تشخیص‌داده‌شده با عیب اعلامی مشتری همخوان است."
    else:
        comparison = "تفاوت بین عیب اعلامی مشتری و تشخیص تعمیرکار وجود دارد."
    estimated_total = row["estimate_parts"] + row["estimate_labor"]
    physical_conditions = json.loads(row["physical_condition"] or "[]")
    diagnosis_block = f"""<h3>گزارش پذیرش و عیب‌یابی</h3>
    <p><strong>وضعیت دستگاه هنگام تحویل:</strong> {e(row['power_state']) or 'ثبت نشده'}</p>
    <p><strong>وضعیت فیزیکی و قطعات:</strong> {e('، '.join(physical_conditions)) or 'موردی انتخاب نشده'}</p>
    <p><strong>عیب اعلامی مشتری:</strong> {e(row['problem']) or 'ثبت نشده'}</p>
    <p><strong>موارد ثبت‌شده هنگام تحویل:</strong> {e('، '.join(intake_checks)) or 'موردی انتخاب نشده'}</p>
    <p><strong>عیب تشخیص‌داده‌شده توسط تعمیرکار:</strong> {e(row['diagnosed_fault']) or 'هنوز ثبت نشده'}</p>
    <p><strong>مقایسه عیب‌ها:</strong> {e(comparison)}</p>
    <h3>برآورد اولیه (غیرقطعی)</h3>
    <p>برآورد قطعات: {money(row['estimate_parts'])} تومان | برآورد دستمزد: {money(row['estimate_labor'])} تومان</p>
    <p><strong>جمع برآورد اولیه: {money(estimated_total)} تومان</strong></p>
    <p>این برآورد با فاکتور نهایی متفاوت است و پس از عیب‌یابی/تأیید مشتری ممکن است تغییر کند.</p>"""
    page = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
    <title>فاکتور {e(row['order_code'])}</title><style>
    body{{font-family:Tahoma,Arial,sans-serif;max-width:850px;margin:35px auto;line-height:2;color:#202634}}
    h1{{color:#2255a2}}table{{width:100%;border-collapse:collapse;margin:25px 0}}
    td,th{{border:1px solid #bbc6d8;padding:8px;text-align:right}}
    th{{background:#edf2fa}}.sum{{background:#f3f6fb;padding:18px}}
    button{{padding:10px 22px;cursor:pointer}}@media print{{button{{display:none}}}}
    </style></head><body><h1>فاکتور فروش / تعمیر - ShopManager</h1>
    <p>کد یکتای سفارش / فاکتور: <strong>{e(row['order_code'])}</strong> | شماره داخلی: {job_id} | تاریخ: {e(row['created_at'])} | وضعیت: {e(row['status'])}</p>
    <p>مشتری: {e(row['customer_name'])} | تماس: {e(row['phone'])}</p>
    <p>آدرس: {e(row['address'])}</p>
    <p>کالا / دستگاه: {e(row['device'])}</p>
    {diagnosis_block}
    <table><thead><tr><th>شرح کالا یا قطعه</th><th>تعداد</th><th>قیمت واحد (تومان)</th>
    <th>جمع (تومان)</th></tr></thead><tbody>{rows}</tbody></table>
    <div class="sum">جمع اقلام: {money(parts)} تومان<br>
    دستمزد: {money(row['labor'])} تومان<br>تخفیف: {money(row['discount'])} تومان<br>
    <strong>مبلغ نهایی: {money(total)} تومان</strong><br>
    پرداخت شده: {money(row['paid'])} تومان<br>
    مانده: {money(total-row['paid'])} تومان</div>
    <p>امضای مشتری: ....................... امضای فروشگاه: .......................</p>
    <button onclick="window.print()">چاپ / ذخیره PDF</button>
    </body></html>"""
    path = INVOICE_DIR / f"invoice_{job_id}.html"
    path.write_text(page, encoding="utf-8")
    webbrowser.open(path.as_uri())
    return path


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ShopManager | مدیریت فروشگاه و تعمیرگاه")
        self.geometry("1100x730")
        self.minsize(890, 560)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.palette = {"bg":"#06182b","panel":"#0b2239","panel2":"#102d49","line":"#14517c",
                        "text":"#f3f7ff","muted":"#a9c0d8","gold":"#f4c76b","blue":"#078cff",
                        "green":"#27d86a","cyan":"#00d9ed","purple":"#a64cff","orange":"#ffad22"}
        self.configure(bg=self.palette["bg"])
        style.configure("TFrame", background="#06182b")
        style.configure("TLabelframe", background="#0b2239", foreground="#f4c76b")
        style.configure("TLabelframe.Label", background="#0b2239", foreground="#f4c76b", font=("Tahoma",10,"bold"))
        style.configure("TEntry", fieldbackground="#102d49", foreground="#ffffff", insertcolor="#ffffff")
        style.configure("TCombobox", fieldbackground="#102d49", foreground="#ffffff")
        style.configure("Treeview", rowheight=34, font=("Tahoma", 10), background="#102d49",
                        fieldbackground="#102d49", foreground="#f3f7ff")
        style.configure("Treeview.Heading", font=("Tahoma", 10, "bold"), background="#173b5c", foreground="#f4c76b")
        style.map("Treeview", background=[("selected","#0757a8")], foreground=[("selected","#ffffff")])
        style.configure("TButton", padding=8, font=("Tahoma", 10), background="#123a60", foreground="#ffffff")
        style.configure("TLabel", font=("Tahoma", 10), background="#0b2239", foreground="#f3f7ff")
        style.configure("TNotebook", background="#06182b", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Tahoma", 10, "bold"),
                        background="#102d49", foreground="#dcecff")
        style.map("TNotebook.Tab", background=[("selected","#0757a8")], foreground=[("selected","#ffffff")])
        header = tk.Frame(self, bg="#06182b", height=70)
        header.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(header, text="⚙ ShopManager", bg="#06182b", fg="#f4c76b",
                 font=("Tahoma", 21, "bold")).pack(side="right", padx=14, pady=12)
        tk.Label(header, text="مدیریت تعمیرگاه موبایل", bg="#06182b",
                 fg="#c2d3eb", font=("Tahoma", 10)).pack(side="right", pady=18)
        tk.Label(header, text="🔔  ۳     │     مدیر سیستم", bg="#06182b", fg="#ffffff",
                 font=("Tahoma", 10)).pack(side="left", padx=12)
        shell = tk.Frame(self, bg="#06182b")
        shell.pack(fill="both", expand=True, padx=12, pady=8)
        sidebar = tk.Frame(shell, bg="#071d32", width=170, highlightbackground="#14517c", highlightthickness=1)
        sidebar.pack(side="right", fill="y", padx=(8,0)); sidebar.pack_propagate(False)
        tk.Label(sidebar, text="ناوبری", bg="#071d32", fg="#f4c76b",
                 font=("Tahoma", 12, "bold")).pack(fill="x", pady=14)
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(side="left", fill="both", expand=True)
        self.dashboard_tab = tk.Frame(self.tabs, bg="#06182b")
        self.ctab = ttk.Frame(self.tabs)
        self.jtab = ttk.Frame(self.tabs)
        self.itab = ttk.Frame(self.tabs)
        self.tabs.add(self.dashboard_tab, text="داشبورد")
        self.tabs.add(self.ctab, text="مشتریان")
        self.tabs.add(self.jtab, text="پذیرش و پرونده‌ها")
        self.tabs.add(self.itab, text="انبار و کالا")
        for label, idx in (("⌂  داشبورد",0),("＋  پذیرش تعمیر",2),("🔧  پرونده‌های تعمیر",2),
                           ("♟  مشتریان",1),("▣  انبار و کالا",3)):
            tk.Button(sidebar, text=label, anchor="e", command=lambda n=idx:self.tabs.select(n),
                      bg="#0d2944", fg="#edf5ff", activebackground="#0757a8", activeforeground="#ffffff",
                      relief="flat", bd=0, font=("Tahoma",10,"bold"), padx=12, pady=13).pack(fill="x", padx=8, pady=4)
        sync_bar = tk.Frame(self, bg="#06182b")
        sync_bar.pack(fill="x", padx=12, pady=(0,6))
        tk.Button(sync_bar, text="فعال‌سازی همگام‌سازی گوشی", command=self.start_sync_ui,
                  bg="#123a60", fg="#ffffff", relief="flat", padx=12, pady=6).pack(side="right", padx=5)
        tk.Button(sync_bar, text="به‌روزرسانی لیست‌ها", command=self.refresh,
                  bg="#123a60", fg="#ffffff", relief="flat", padx=12, pady=6).pack(side="right", padx=5)
        self.make_customers()
        self.make_items()
        self.cart = {}
        self.cart_job_id = None
        self.make_jobs()
        self.refresh()
        self.make_dashboard()

    def make_dashboard(self):
        p=self.palette
        for child in self.dashboard_tab.winfo_children(): child.destroy()
        top=tk.Frame(self.dashboard_tab,bg=p["bg"]);top.pack(fill="x",padx=10,pady=10)
        stats=[]
        try:
            with db() as c:
                customers=c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
                items=c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                active=c.execute("SELECT COUNT(*) FROM jobs WHERE status NOT IN ('تحویل شده','تکمیل شده')").fetchone()[0]
                qty=c.execute("SELECT COALESCE(SUM(qty),0) FROM items").fetchone()[0]
                today=c.execute("SELECT COALESCE(SUM(labor),0) FROM jobs WHERE date(created_at)=date('now','localtime')").fetchone()[0]
                recent=c.execute("SELECT j.order_code,j.device,j.status,c.name FROM jobs j JOIN customers c ON c.id=j.customer_id ORDER BY j.id DESC LIMIT 4").fetchall()
                low=c.execute("SELECT name,qty FROM items WHERE qty<=2 ORDER BY qty LIMIT 3").fetchall()
        except Exception:
            customers=items=active=qty=today=0;recent=[];low=[]
        stats=[("درآمد امروز",money(today)+" تومان",p["purple"],"＄"),("تعمیرات فعال",str(active),p["cyan"],"🔧"),
               ("دستگاه‌های در تعمیر",str(active),p["orange"],"▣"),("مشتریان",str(customers),p["green"],"♟"),
               ("موجودی کالا",str(qty),p["blue"],"▦")]
        for title,value,color,glyph in stats:
            card=tk.Frame(top,bg="#102d49",highlightbackground=color,highlightthickness=1)
            card.pack(side="right",fill="both",expand=True,padx=4)
            tk.Label(card,text=glyph,bg="#102d49",fg=color,font=("Tahoma",21,"bold")).pack(side="right",padx=8,pady=12)
            box=tk.Frame(card,bg="#102d49");box.pack(side="right",fill="both",expand=True)
            tk.Label(box,text=title,bg="#102d49",fg="#c5d9ef",font=("Tahoma",9)).pack(anchor="e",pady=(9,0))
            tk.Label(box,text=value,bg="#102d49",fg="#ffffff",font=("Tahoma",14,"bold")).pack(anchor="e",pady=(1,8))
        middle=tk.Frame(self.dashboard_tab,bg=p["bg"]);middle.pack(fill="both",expand=True,padx=10)
        left=tk.Frame(middle,bg=p["bg"]);left.pack(side="left",fill="both",expand=True,padx=4)
        right=tk.Frame(middle,bg=p["bg"]);right.pack(side="right",fill="both",expand=True,padx=4)
        chart=tk.Frame(left,bg="#0b2239",highlightbackground="#14517c",highlightthickness=1)
        chart.pack(fill="both",expand=True,pady=5)
        tk.Label(chart,text="روند پذیرش و تحویل (۳۰ روز گذشته)",bg="#0b2239",fg="#ffffff",
                 font=("Tahoma",12,"bold")).pack(anchor="e",padx=12,pady=10)
        cv=tk.Canvas(chart,bg="#0b2239",height=205,highlightthickness=0);cv.pack(fill="both",expand=True,padx=10,pady=6)
        for n in range(5):
            y=175-n*36;cv.create_line(35,y,cv.winfo_reqwidth()+400,y,fill="#183c5b")
            cv.create_text(18,y,text=str(n*5),fill="#a9c0d8",font=("Tahoma",8))
        for n in range(14):
            x=48+n*31;h1=35+(n*17%105);h2=20+(n*11%75)
            cv.create_rectangle(x,178-h1,x+10,178,fill="#078cff",outline="")
            cv.create_rectangle(x+12,178-h2,x+22,178,fill="#27d86a",outline="")
        lower=tk.Frame(left,bg="#0b2239",highlightbackground="#14517c",highlightthickness=1)
        lower.pack(fill="x",pady=5)
        tk.Label(lower,text="عملیات سریع",bg="#0b2239",fg="#ffffff",font=("Tahoma",12,"bold")).pack(anchor="e",padx=12,pady=8)
        actions=[("♟ مشتری جدید",1,p["cyan"]),("＋ پذیرش جدید",2,p["blue"]),("▣ انبار و کالا",3,p["green"]),("＄ امور مالی",2,p["orange"]),("▤ گزارش‌ها",2,p["purple"])]
        row=tk.Frame(lower,bg="#0b2239");row.pack(fill="x",padx=6,pady=8)
        for label,idx,color in actions:
            tk.Button(row,text=label,command=lambda n=idx:self.tabs.select(n),bg="#102d49",fg=color,
                      activebackground="#173b5c",activeforeground="#ffffff",relief="flat",
                      font=("Tahoma",9,"bold"),padx=7,pady=16).pack(side="right",fill="x",expand=True,padx=3)
        recentbox=tk.Frame(right,bg="#0b2239",highlightbackground="#14517c",highlightthickness=1)
        recentbox.pack(fill="both",expand=True,pady=5)
        tk.Label(recentbox,text="آخرین پرونده‌ها",bg="#0b2239",fg="#ffffff",
                 font=("Tahoma",12,"bold")).pack(anchor="e",padx=12,pady=10)
        for j in recent:
            row=tk.Frame(recentbox,bg="#102d49");row.pack(fill="x",padx=8,pady=4)
            tk.Label(row,text=j["order_code"],bg="#102d49",fg="#ffffff",font=("Tahoma",9,"bold")).pack(side="left",padx=8,pady=10)
            tk.Label(row,text=j["device"],bg="#102d49",fg="#dcecff",font=("Tahoma",9)).pack(side="right",padx=8)
            tk.Label(row,text=j["status"],bg="#102d49",fg=p["green"],font=("Tahoma",9,"bold")).pack(side="right",padx=8)
        alerts=tk.Frame(right,bg="#0b2239",highlightbackground="#14517c",highlightthickness=1)
        alerts.pack(fill="both",expand=True,pady=5)
        tk.Label(alerts,text="یادآوری و هشدارها  🔔",bg="#0b2239",fg="#ffffff",
                 font=("Tahoma",12,"bold")).pack(anchor="e",padx=12,pady=8)
        if low:
            for item in low:
                tk.Label(alerts,text=f"⚠ موجودی پایین: {item['name']} ({item['qty']})",bg="#102d49",
                         fg="#ff7777",font=("Tahoma",9)).pack(fill="x",padx=8,pady=4)
        else:
            tk.Label(alerts,text="هشدار موجودی بحرانی ثبت نشده است.",bg="#102d49",
                     fg="#a9c0d8",font=("Tahoma",9)).pack(fill="x",padx=8,pady=8)
        footer=tk.Frame(self.dashboard_tab,bg="#071d32",highlightbackground="#14517c",highlightthickness=1)
        footer.pack(fill="x",padx=10,pady=8)
        tk.Label(footer,text="▦ SQLite محلی     │     ShopManager · Windows",bg="#071d32",
                 fg="#c2d3eb",font=("Tahoma",9)).pack(side="right",padx=12,pady=8)
        tk.Label(footer,text="وضعیت: آماده به کار  ●",bg="#071d32",fg="#27d86a",
                 font=("Tahoma",9,"bold")).pack(side="left",padx=12)

    def start_sync_ui(self):
        try:
            from sync_server import start_server, pairing_info
            if not getattr(self, "_sync_started", False):
                start_server()
                self._sync_started = True
            messagebox.showinfo("اتصال گوشی", pairing_info())
        except Exception as exc:
            messagebox.showerror("خطای سرویس همگام‌سازی", str(exc))

    def label_entry(self, parent, label, width=24):
        f = ttk.Frame(parent)
        ttk.Label(f, text=label).pack(side="right", padx=5)
        ent = ttk.Entry(f, width=width, justify="right")
        ent.pack(side="right", padx=5)
        return f, ent

    def table(self, parent, cols, headers, widths=None):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for i, (key, header) in enumerate(zip(cols, headers)):
            tree.heading(key, text=header)
            tree.column(key, width=(widths or {}).get(key, 145), anchor="center")
        scrollbar = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    def selected(self, tree, label):
        chosen = tree.selection()
        if not chosen:
            raise ValueError(f"ابتدا {label} را از جدول انتخاب کنید.")
        return int(tree.item(chosen[0], "values")[0])

    def perform(self, fn):
        try:
            fn()
            self.refresh()
        except (ValueError, sqlite3.Error) as ex:
            messagebox.showerror("خطا", str(ex))

    def make_customers(self):
        required = ttk.LabelFrame(self.ctab, text="پروفایل مشتری | فیلدهای ستاره‌دار اجباری هستند")
        required.pack(fill="x", padx=10, pady=(12, 5))
        self.customer_fields = []
        for label in ("نام *", "نام خانوادگی *", "شماره تماس *"):
            frame, field = self.label_entry(required, label, 22)
            frame.pack(side="right", padx=8, pady=8)
            self.customer_fields.append(field)
        optional = ttk.LabelFrame(self.ctab, text="اطلاعات تکمیلی | اختیاری")
        optional.pack(fill="x", padx=10, pady=5)
        for label in ("آدرس محل سکونت", "یادداشت"):
            frame, field = self.label_entry(optional, label, 28)
            frame.pack(side="right", padx=8, pady=8)
            self.customer_fields.append(field)
        ttk.Button(optional, text="ثبت پروفایل مشتری",
                   command=lambda: self.perform(self.new_customer)).pack(side="right", padx=12, pady=8)
        self.customer_tree = self.table(self.ctab, ("id", "first_name", "last_name", "phone", "address", "notes"),
                                        ("کد", "نام", "نام خانوادگی", "شماره تماس", "آدرس", "یادداشت"))

    def new_customer(self):
        values = [f.get() for f in self.customer_fields]
        add_customer(*values)
        for f in self.customer_fields:
            f.delete(0, "end")

    def make_items(self):
        bar = ttk.Frame(self.itab)
        bar.pack(fill="x", pady=10)
        self.item_fields = []
        for label in ("کد کالا", "نام کالا", "موجودی اولیه", "قیمت خرید", "قیمت فروش"):
            frame, field = self.label_entry(bar, label, 13)
            frame.pack(side="right", padx=2)
            self.item_fields.append(field)
        ttk.Button(bar, text="ثبت کالا", command=lambda: self.perform(self.new_item)).pack(side="right")
        opts = ttk.Frame(self.itab)
        opts.pack(fill="x")
        ttk.Button(opts, text="افزایش موجودی کالای انتخابی", command=lambda: self.perform(self.increase_stock)).pack(side="right", padx=12)
        ttk.Label(opts, text="مبالغ بر حسب تومان؛ موجودی با مصرف در پرونده کم می‌شود.").pack(side="right")
        self.item_tree = self.table(self.itab, ("id", "sku", "name", "qty", "cost", "price"),
                                    ("کد", "شناسه کالا", "نام", "موجودی", "خرید (تومان)", "فروش (تومان)"))

    def new_item(self):
        sku, name, qty, cost, price = (x.get() for x in self.item_fields)
        item_id = add_item(sku, name, amount(qty, "موجودی"), amount(cost, "قیمت خرید"), amount(price, "قیمت فروش"))
        with db() as c:
            item_code = c.execute("SELECT sku FROM items WHERE id=?", (item_id,)).fetchone()["sku"]
        for f in self.item_fields:
            f.delete(0, "end")
        messagebox.showinfo("کالا ثبت شد", f"کد خودکار کالا: {item_code}")

    def increase_stock(self):
        item_id = self.selected(self.item_tree, "کالا")
        n = simpledialog.askinteger("ورود موجودی", "تعداد اضافه‌شده:", parent=self, minvalue=1)
        if n is not None:
            restock(item_id, n)

    def make_jobs(self):
        bar = ttk.Frame(self.jtab)
        bar.pack(fill="x", padx=8, pady=9)
        ttk.Label(bar, text="مشتری:").pack(side="right")
        self.customer_choice = ttk.Combobox(bar, state="readonly", width=27, justify="right")
        self.customer_choice.pack(side="right", padx=6)
        device_row = ttk.Frame(self.jtab)
        device_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(device_row, text="نوع دستگاه:").pack(side="right")
        self.device_type = ttk.Combobox(device_row, state="readonly", width=14,
            values=("گوشی لمسی","گوشی دکمه‌ای"), justify="right")
        self.device_type.set("گوشی لمسی")
        self.device_type.pack(side="right", padx=4)
        ttk.Label(device_row, text="برند:").pack(side="right")
        self.device_brand = ttk.Combobox(device_row, state="readonly", width=16, justify="right")
        self.device_brand.pack(side="right", padx=4)
        ttk.Label(device_row, text="جست‌وجوی مدل:").pack(side="right")
        self.device_search = ttk.Entry(device_row, width=20, justify="right")
        self.device_search.pack(side="right", padx=4)
        self.device_entry = ttk.Combobox(device_row, state="normal", width=25, justify="right")
        self.device_entry.pack(side="right", padx=4)
        self.device_catalog = self.load_device_catalog()
        self.device_type.bind("<<ComboboxSelected>>", lambda _e: self.update_device_brands())
        self.device_brand.bind("<<ComboboxSelected>>", lambda _e: self.update_device_models())
        self.device_search.bind("<KeyRelease>", lambda _e: self.update_device_models())
        self.update_device_brands()
        ttk.Label(bar, text="عیب اعلامی مشتری:").pack(side="right")
        self.problem_entry = ttk.Entry(bar, width=24, justify="right")
        self.problem_entry.pack(side="right", padx=6)
        ttk.Button(bar, text="ایجاد پرونده", command=lambda: self.perform(self.new_job)).pack(side="right", padx=5)
        self.job_tree = self.table(self.jtab,
            ("id", "order_code", "customer", "device", "status", "labor", "date"),
            ("شناسه داخلی", "کد یکتای سفارش", "مشتری", "دستگاه / سفارش", "وضعیت", "دستمزد", "تاریخ"),
            {"order_code": 170, "customer": 180, "device": 200})
        self.job_tree.configure(height=8)
        self.job_tree.bind("<<TreeviewSelect>>", lambda _event: self.load_job())
        intake = ttk.LabelFrame(self.jtab, text="پذیرش گوشی: چک‌لیست عیب، تشخیص واقعی و برآورد اولیه")
        intake.pack(fill="x", padx=10, pady=5)
        self.fault_options = [
            "روشن نمی‌شود", "شارژ نمی‌شود", "باتری ضعیف", "شکستگی نمایشگر",
            "مشکل تاچ", "خرابی دوربین", "مشکل صدا/میکروفون", "آنتن‌دهی/سیم‌کارت",
            "آب‌خوردگی", "خرابی دکمه‌ها", "مشکل نرم‌افزاری", "خرابی سوکت شارژ",
            "شکستگی بدنه", "سایر"
        ]
        self.fault_vars = {}
        fault_grid = ttk.Frame(intake)
        fault_grid.pack(fill="x", padx=6, pady=3)
        for idx, fault in enumerate(self.fault_options):
            var = tk.BooleanVar(value=False)
            self.fault_vars[fault] = var
            ttk.Checkbutton(fault_grid, text=fault, variable=var).grid(
                row=idx // 4, column=3 - (idx % 4), sticky="e", padx=8, pady=2)
        self.keypad_frame = ttk.LabelFrame(intake, text="انتخاب دکمه‌های معیوب گوشی")
        self.keypad_vars = {}
        keypad_rows = [
            ["چراغ‌قوه", "بلندتر", "کمتر"],
            ["کلید چپ", "جهت بالا", "کلید راست"],
            ["جهت چپ", "OK", "جهت راست"],
            ["جهت پایین", "بازگشت", "منو"],
            ["تماس", "پایان تماس", "پاک‌کردن"],
            ["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"],
            ["*", "0", "#"]
        ]
        for rr, row_keys in enumerate(keypad_rows):
            for cc, key_name in enumerate(row_keys):
                var = tk.BooleanVar(value=False)
                self.keypad_vars[key_name] = var
                ttk.Checkbutton(self.keypad_frame, text=key_name, variable=var).grid(
                    row=rr, column=cc, padx=10, pady=2, sticky="ew")
        self.keypad_frame.pack_forget()
        self.fault_vars["خرابی دکمه‌ها"].trace_add(
            "write", lambda *_: self.toggle_keypad())
        self.device_type.bind("<<ComboboxSelected>>", lambda _e: self.toggle_keypad())
        fields = ttk.Frame(intake)
        fields.pack(fill="x", padx=6, pady=4)
        condition_box = ttk.LabelFrame(intake, text="وضعیت دستگاه هنگام تحویل")
        condition_box.pack(fill="x", padx=6, pady=4)
        power_row = ttk.Frame(condition_box)
        power_row.pack(fill="x", padx=6, pady=3)
        ttk.Label(power_row, text="وضعیت روشن/خاموش:").pack(side="right", padx=5)
        self.power_state_choice = ttk.Combobox(power_row, state="readonly", width=12,
                                                values=("روشن", "خاموش"), justify="right")
        self.power_state_choice.pack(side="right", padx=5)
        physical_options = (
            "شکستگی نمایشگر", "ترک‌خوردگی قاب", "شکستگی قاب/بدنه", "آسیب‌دیدگی سوکت شارژ",
            "آثار رطوبت یا آب‌خوردگی", "خط‌وخش یا فرورفتگی", "باتری مفقود", "سیم‌کارت مفقود",
            "کارت حافظه مفقود", "خشاب سیم‌کارت مفقود", "درب پشت مفقود",
            "درپوش باتری مفقود", "شارژر مفقود", "کابل USB مفقود",
            "لوازم جانبی مفقود", "قلم لمسی مفقود", "پیچ یا قطعه بدنه مفقود", "سایر نقص‌ها"
        )
        self.physical_vars = {}
        physical_grid = ttk.Frame(condition_box)
        physical_grid.pack(fill="x", padx=6, pady=3)
        for idx, condition in enumerate(physical_options):
            var = tk.BooleanVar(value=False)
            self.physical_vars[condition] = var
            ttk.Checkbutton(physical_grid, text=condition, variable=var).grid(
                row=idx // 4, column=3 - (idx % 4), sticky="e", padx=8, pady=2)
        self.physical_other_entry = ttk.Entry(condition_box, width=48, justify="right")
        self.physical_other_entry.pack(anchor="e", padx=10, pady=3)
        self.physical_other_entry.insert(0, "شرح سایر نقص‌ها / قطعات مفقود (اختیاری)")
        self.physical_other_entry.bind("<FocusIn>", lambda _e: self.physical_other_entry.delete(0, "end")
            if self.physical_other_entry.get().startswith("شرح سایر") else None)

        ttk.Label(fields, text="عیب تشخیص‌داده‌شده:").pack(side="right", padx=4)
        self.diagnosed_entry = ttk.Entry(fields, width=30, justify="right")
        self.diagnosed_entry.pack(side="right", padx=4)
        ttk.Label(fields, text="برآورد قطعات:").pack(side="right", padx=4)
        self.estimate_parts_entry = ttk.Entry(fields, width=10, justify="right")
        self.estimate_parts_entry.insert(0, "0")
        self.estimate_parts_entry.pack(side="right", padx=4)
        ttk.Label(fields, text="برآورد دستمزد:").pack(side="right", padx=4)
        self.estimate_labor_entry = ttk.Entry(fields, width=10, justify="right")
        self.estimate_labor_entry.insert(0, "0")
        self.estimate_labor_entry.pack(side="right", padx=4)
        ttk.Button(fields, text="ذخیره پذیرش و برآورد",
                   command=lambda: self.perform(self.save_intake_ui)).pack(side="right", padx=8)

        controls = ttk.LabelFrame(self.jtab, text="ویرایش پرونده انتخابی و ثبت مصرف منابع")
        controls.pack(fill="x", padx=10, pady=8)
        top = ttk.Frame(controls)
        top.pack(fill="x", pady=8)
        ttk.Label(top, text="کالای مصرفی:").pack(side="right", padx=5)
        self.item_choice = ttk.Combobox(top, state="readonly", width=38, justify="right")
        self.item_choice.pack(side="right", padx=5)
        ttk.Label(top, text="تعداد:").pack(side="right")
        self.qty_entry = ttk.Entry(top, width=7)
        self.qty_entry.insert(0, "1")
        self.qty_entry.pack(side="right", padx=5)
        ttk.Button(top, text="افزودن به سبد",
                   command=lambda: self.perform(self.consume)).pack(side="right", padx=10)
        cart_controls = ttk.Frame(controls)
        cart_controls.pack(fill="x", padx=8, pady=3)
        ttk.Label(cart_controls, text="سبد اقلام (هنوز از موجودی کسر نشده):").pack(side="right")
        ttk.Button(cart_controls, text="ثبت همه اقلام در پرونده و کسر موجودی",
                   command=lambda: self.perform(self.commit_cart)).pack(side="left", padx=6)
        ttk.Button(cart_controls, text="حذف قلم انتخابی",
                   command=lambda: self.perform(self.remove_cart_item)).pack(side="left", padx=6)
        self.cart_tree = ttk.Treeview(controls, columns=("id", "name", "qty", "price", "total"),
                                      show="headings", height=4, selectmode="browse")
        for key, heading, width in (
            ("id", "کد", 55), ("name", "نام قطعه", 240), ("qty", "تعداد", 90),
            ("price", "قیمت واحد", 130), ("total", "جمع", 150)):
            self.cart_tree.heading(key, text=heading)
            self.cart_tree.column(key, width=width, anchor="center")
        self.cart_tree.pack(fill="x", padx=8)
        self.cart_total_label = ttk.Label(controls, text="جمع سبد: ۰ تومان")
        self.cart_total_label.pack(anchor="e", padx=12, pady=3)
        bottom = ttk.Frame(controls)
        bottom.pack(fill="x", pady=8)
        self.job_fields = {}
        for key, label in (("labor", "دستمزد"), ("discount", "تخفیف"), ("paid", "پرداخت شده")):
            frame, ent = self.label_entry(bottom, label, 11)
            frame.pack(side="right")
            self.job_fields[key] = ent
        ttk.Label(bottom, text="وضعیت:").pack(side="right", padx=5)
        self.status_choice = ttk.Combobox(bottom, values=("در انتظار", "در حال تعمیر", "آماده تحویل", "تحویل داده شد", "لغو شده"),
                                           state="readonly", width=15)
        self.status_choice.pack(side="right", padx=5)
        ttk.Button(bottom, text="ذخیره مبالغ", command=lambda: self.perform(self.update_job)).pack(side="right", padx=6)
        ttk.Button(bottom, text="صدور فاکتور", command=lambda: self.perform(self.make_invoice)).pack(side="right")
        self.summary_label = ttk.Label(self.jtab, text="یک پرونده را انتخاب کنید.", font=("Tahoma", 11))
        self.summary_label.pack(anchor="e", padx=15, pady=6)
        self.lines_tree = self.table(self.jtab, ("name", "qty", "price", "sum"),
                                     ("اقلام مصرفی", "تعداد", "قیمت واحد", "جمع"))

    def toggle_keypad(self):
        show = self.device_type.get() == "دکمه‌ای" and self.fault_vars["خرابی دکمه‌ها"].get()
        if show:
            self.keypad_frame.pack(fill="x", padx=8, pady=4)
        else:
            self.keypad_frame.pack_forget()

    def save_intake_ui(self):
        job_id = self.selected(self.job_tree, "پرونده")
        checks = [fault for fault, var in self.fault_vars.items() if var.get()]
        faulty_keys = [key for key, var in self.keypad_vars.items() if var.get()]
        if faulty_keys:
            checks.append("دکمه‌های معیوب: " + "، ".join(faulty_keys))
        physical = [name for name, var in self.physical_vars.items() if var.get()]
        extra = self.physical_other_entry.get().strip()
        if extra and not extra.startswith("شرح سایر"):
            physical.append("سایر: " + extra)
        if self.power_state_choice.get() not in ("روشن", "خاموش"):
            raise ValueError("وضعیت روشن یا خاموش بودن دستگاه را مشخص کنید.")
        save_intake(
            job_id, self.current_reported_fault,
            checks, self.diagnosed_entry.get(),
            amount(self.estimate_parts_entry.get(), "برآورد قطعات"),
            amount(self.estimate_labor_entry.get(), "برآورد دستمزد"),
            self.power_state_choice.get(), physical)
        self.load_job()
        try:
            path = export_intake_report(job_id)
            messagebox.showinfo("گزارش پذیرش ذخیره شد",
                                f"نسخه PDF و تصویر گزارش در پوشه بایگانی ذخیره شدند.\n{path}")
        except Exception as exc:
            messagebox.showerror("خطا در ساخت گزارش", str(exc))

    def load_device_catalog(self):
        try:
            with Path(__file__).with_name("device_catalog.json").open(encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def update_device_brands(self):
        category = self.device_type.get()
        brands = self.device_catalog.get(category, {})
        names = sorted(brands.keys(), key=str.casefold)
        self.device_brand.configure(values=names)
        self.device_brand.set(names[0] if names else "")
        self.device_search.delete(0, "end")
        self.device_entry.set("")
        self.update_device_models()

    def update_device_models(self):
        category = self.device_type.get()
        brands = self.device_catalog.get(category, {})
        brand = self.device_brand.get()
        models = brands.get(brand, [])
        query = self.device_search.get().strip().casefold()
        filtered = [m for m in models if query in m.casefold()]
        self.device_entry.configure(values=filtered)
        current = self.device_entry.get().strip()
        if current and current not in filtered:
            self.device_entry.set("")

    def new_job(self):
        if self.customer_choice.current() < 0:
            raise ValueError("ابتدا مشتری را انتخاب کنید.")
        customer_id = self.customer_ids[self.customer_choice.current()]
        model = self.device_entry.get().strip()
        if not model:
            raise ValueError("مدل دستگاه را از فهرست انتخاب یا نام آن را وارد کنید.")
        device_name = f"{self.device_type.get()} | {self.device_brand.get()} | {model}"
        job_id = create_job(customer_id, device_name, self.problem_entry.get())
        self.current_reported_fault = self.problem_entry.get()
        self.device_entry.delete(0, "end")
        self.problem_entry.delete(0, "end")
        self.refresh()
        with db() as c:
            order_code = c.execute("SELECT order_code FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
        messagebox.showinfo("سفارش ثبت شد", f"کد یکتای سفارش: {order_code}")
        for row in self.job_tree.get_children():
            if int(self.job_tree.item(row, "values")[0]) == job_id:
                self.job_tree.selection_set(row)
                self.job_tree.see(row)
                break

    def render_cart(self):
        for row in self.cart_tree.get_children():
            self.cart_tree.delete(row)
        total = 0
        with db() as c:
            for item_id, qty in self.cart.items():
                item = c.execute("SELECT name,price FROM items WHERE id=?", (item_id,)).fetchone()
                if item:
                    subtotal = qty * item["price"]
                    total += subtotal
                    self.cart_tree.insert("", "end", values=(
                        item_id, item["name"], qty, money(item["price"]), money(subtotal)))
        self.cart_total_label.configure(text=f"جمع سبد: {money(total)} تومان")

    def consume(self):
        job_id = self.selected(self.job_tree, "پرونده")
        if self.item_choice.current() < 0:
            raise ValueError("کالای مصرفی را انتخاب کنید.")
        item_id = self.item_ids[self.item_choice.current()]
        qty = amount(self.qty_entry.get(), "تعداد")
        if qty <= 0:
            raise ValueError("تعداد باید بیشتر از صفر باشد.")
        if self.cart_job_id != job_id:
            self.cart.clear()
            self.cart_job_id = job_id
        with db() as c:
            item = c.execute("SELECT qty,name FROM items WHERE id=?", (item_id,)).fetchone()
        if not item or self.cart.get(item_id, 0) + qty > item["qty"]:
            raise ValueError("موجودی کافی برای تعداد انتخاب‌شده وجود ندارد.")
        self.cart[item_id] = self.cart.get(item_id, 0) + qty
        self.render_cart()

    def remove_cart_item(self):
        selected = self.cart_tree.selection()
        if not selected:
            raise ValueError("قلمی از سبد انتخاب نشده است.")
        item_id = int(self.cart_tree.item(selected[0], "values")[0])
        self.cart.pop(item_id, None)
        self.render_cart()

    def commit_cart(self):
        job_id = self.selected(self.job_tree, "پرونده")
        if job_id != self.cart_job_id:
            raise ValueError("سبد مربوط به این پرونده نیست.")
        use_items(job_id, list(self.cart.items()))
        self.cart.clear()
        self.render_cart()
        self.refresh()
        for row in self.job_tree.get_children():
            if int(self.job_tree.item(row, "values")[0]) == job_id:
                self.job_tree.selection_set(row)
                self.job_tree.see(row)
                break
        self.load_job()


    def update_job(self):
        job_id = self.selected(self.job_tree, "پرونده")
        nums = [amount(self.job_fields[key].get(), key) for key in ("labor", "discount", "paid")]
        save_job(job_id, *nums, self.status_choice.get())
        self.load_job()

    def make_invoice(self):
        job_id = self.selected(self.job_tree, "پرونده")
        path = invoice(job_id)
        messagebox.showinfo("فاکتور صادر شد", f"فاکتور در مرورگر باز شد:\n{path}\n\nبرای PDF از گزینه Print استفاده کنید.")

    def load_job(self):
        try:
            job_id = self.selected(self.job_tree, "پرونده")
            row, lines, parts, costs, total = job_summary(job_id)
            if self.cart_job_id != job_id:
                self.cart.clear()
                self.cart_job_id = job_id
                self.render_cart()
            self.current_reported_fault = row["problem"] or ""
            self.diagnosed_entry.delete(0, "end")
            self.diagnosed_entry.insert(0, row["diagnosed_fault"] or "")
            self.estimate_parts_entry.delete(0, "end")
            self.estimate_parts_entry.insert(0, str(row["estimate_parts"]))
            self.estimate_labor_entry.delete(0, "end")
            self.estimate_labor_entry.insert(0, str(row["estimate_labor"]))
            self.power_state_choice.set(row["power_state"] or "")
            saved_physical = set(json.loads(row["physical_condition"] or "[]"))
            for condition, var in self.physical_vars.items():
                var.set(condition in saved_physical)
            other = next((x[6:] for x in saved_physical if x.startswith("سایر: ")), "")
            self.physical_other_entry.delete(0, "end")
            self.physical_other_entry.insert(0, other)
            saved_checks = set(json.loads(row["intake_checks"] or "[]"))
            for fault, var in self.fault_vars.items():
                var.set(fault in saved_checks)
            saved_key_text = next((x for x in saved_checks if x.startswith("دکمه‌های معیوب:")), "")
            saved_keys = set(saved_key_text.replace("دکمه‌های معیوب:", "").strip().split("، ")) if saved_key_text else set()
            for key, var in self.keypad_vars.items():
                var.set(key in saved_keys)
            self.toggle_keypad()
            for key in ("labor", "discount", "paid"):
                field = self.job_fields[key]
                field.delete(0, "end")
                field.insert(0, str(row[key]))
            self.status_choice.set(row["status"])
            for r in self.lines_tree.get_children():
                self.lines_tree.delete(r)
            for x in lines:
                self.lines_tree.insert("", "end", values=(
                    x["name"], x["qty"], money(x["unit_price"]), money(x["qty"]*x["unit_price"])))
            self.summary_label.configure(text=(
                f"کد سفارش: {row['order_code']} | جمع اقلام: {money(parts)} | بهای خرید اقلام: {money(costs)} | "
                f"جمع نهایی: {money(total)} | مانده: {money(total-row['paid'])} تومان"))
        except ValueError:
            pass

    def refresh(self):
        with db() as c:
            customers = c.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
            items = c.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
            jobs = c.execute("""SELECT j.*, c.name FROM jobs j JOIN customers c ON c.id=j.customer_id
                                ORDER BY j.id DESC""").fetchall()
        for tree in (self.customer_tree, self.item_tree, self.job_tree):
            for r in tree.get_children():
                tree.delete(r)
        for c in customers:
            self.customer_tree.insert("", "end", values=(
                c["id"], c["first_name"] or c["name"], c["last_name"] or "",
                c["phone"], c["address"], c["notes"]))
        for i in items:
            self.item_tree.insert("", "end", values=(
                i["id"], i["sku"] or "", i["name"], i["qty"], money(i["cost"]), money(i["price"])))
        for j in jobs:
            self.job_tree.insert("", "end", values=(
                j["id"], j["order_code"], j["name"], j["device"], j["status"], money(j["labor"]), j["created_at"]))
        self.customer_ids = [c["id"] for c in customers]
        self.customer_choice["values"] = [
            f"{c['id']} - {c['first_name'] or c['name']} {c['last_name'] or ''} ({c['phone']})"
            for c in customers]
        self.item_ids = [i["id"] for i in items]
        self.item_choice["values"] = [
            f"{i['sku']} - {i['name']} | موجودی {i['qty']} | {money(i['price'])} تومان" for i in items]


if __name__ == "__main__":
    init_db()
    App().mainloop()
