# -*- coding: utf-8 -*-
"""ShopManager - offline customer, inventory, repair and invoice manager."""
import html
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
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT DEFAULT '',
          address TEXT DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS items(
          id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT NOT NULL,
          qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0),
          cost INTEGER NOT NULL DEFAULT 0 CHECK(cost>=0),
          price INTEGER NOT NULL DEFAULT 0 CHECK(price>=0));
        CREATE TABLE IF NOT EXISTS jobs(
          id INTEGER PRIMARY KEY, order_code TEXT UNIQUE, customer_id INTEGER NOT NULL REFERENCES customers(id),
          device TEXT NOT NULL DEFAULT '', problem TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'در انتظار', labor INTEGER NOT NULL DEFAULT 0,
          discount INTEGER NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, notes TEXT DEFAULT '');
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
        columns = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        if "order_code" not in columns:
            c.execute("ALTER TABLE jobs ADD COLUMN order_code TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_order_code ON jobs(order_code)")
        for job in c.execute("SELECT id, created_at FROM jobs WHERE order_code IS NULL OR order_code=''").fetchall():
            year = (job["created_at"] or "")[:4]
            if not (len(year) == 4 and year.isdigit()):
                year = "0000"
            c.execute("UPDATE jobs SET order_code=? WHERE id=?",
                      (f"SM-{year}-{job['id']:06d}", job["id"]))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def add_customer(name, phone="", address="", notes=""):
    if not name.strip():
        raise ValueError("نام مشتری الزامی است.")
    with db() as c:
        return c.execute("INSERT INTO customers(name,phone,address,notes) VALUES(?,?,?,?)",
                         (name.strip(), phone.strip(), address.strip(), notes.strip())).lastrowid


def add_item(sku, name, qty, cost, price):
    if not name.strip():
        raise ValueError("نام کالا الزامی است.")
    with db() as c:
        cur = c.execute("INSERT INTO items(sku,name,qty,cost,price) VALUES(?,?,?,?,?)",
                        (sku.strip() or None, name.strip(), qty, cost, price))
        if qty:
            c.execute("INSERT INTO stock_log(item_id,change_qty,reason,created_at) VALUES(?,?,?,?)",
                      (cur.lastrowid, qty, "موجودی اولیه", now()))
        return cur.lastrowid


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
        SELECT j.*,c.name AS customer_name,c.phone,c.address
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


def invoice(job_id):
    row, lines, parts, costs, total = job_summary(job_id)
    e = lambda v: html.escape(str(v or ""))
    rows = "".join(
        f"<tr><td>{e(x['name'])}</td><td>{x['qty']}</td><td>{money(x['unit_price'])}</td>"
        f"<td>{money(x['qty']*x['unit_price'])}</td></tr>" for x in lines)
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
    <p>کالا / دستگاه: {e(row['device'])} | شرح درخواست: {e(row['problem'])}</p>
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
        style.configure("Treeview", rowheight=29, font=("Tahoma", 10))
        style.configure("TButton", padding=7, font=("Tahoma", 10))
        style.configure("TLabel", font=("Tahoma", 10))
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=12)
        self.ctab = ttk.Frame(tabs)
        self.itab = ttk.Frame(tabs)
        self.jtab = ttk.Frame(tabs)
        tabs.add(self.jtab, text="پرونده‌ها و فاکتور")
        tabs.add(self.itab, text="کالاها و منابع")
        tabs.add(self.ctab, text="مشتریان")
        self.make_customers()
        self.make_items()
        self.cart = {}
        self.cart_job_id = None
        self.make_jobs()
        self.refresh()

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
        bar = ttk.Frame(self.ctab)
        bar.pack(fill="x", pady=12)
        self.customer_fields = []
        for label in ("نام مشتری", "شماره تماس", "آدرس", "توضیحات"):
            frame, field = self.label_entry(bar, label, 17)
            frame.pack(side="right", padx=4)
            self.customer_fields.append(field)
        ttk.Button(bar, text="ثبت مشتری", command=lambda: self.perform(self.new_customer)).pack(side="right", padx=10)
        self.customer_tree = self.table(self.ctab, ("id", "name", "phone", "address", "notes"),
                                        ("کد", "نام", "تماس", "آدرس", "یادداشت"))

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
        add_item(sku, name, amount(qty, "موجودی"), amount(cost, "قیمت خرید"), amount(price, "قیمت فروش"))
        for f in self.item_fields:
            f.delete(0, "end")

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
        ttk.Label(bar, text="کالا / دستگاه:").pack(side="right")
        self.device_entry = ttk.Entry(bar, width=23, justify="right")
        self.device_entry.pack(side="right", padx=6)
        ttk.Label(bar, text="شرح درخواست:").pack(side="right")
        self.problem_entry = ttk.Entry(bar, width=29, justify="right")
        self.problem_entry.pack(side="right", padx=6)
        ttk.Button(bar, text="ایجاد پرونده", command=lambda: self.perform(self.new_job)).pack(side="right", padx=5)
        self.job_tree = self.table(self.jtab,
            ("id", "order_code", "customer", "device", "status", "labor", "date"),
            ("شناسه داخلی", "کد یکتای سفارش", "مشتری", "دستگاه / سفارش", "وضعیت", "دستمزد", "تاریخ"),
            {"order_code": 170, "customer": 180, "device": 200})
        self.job_tree.configure(height=8)
        self.job_tree.bind("<<TreeviewSelect>>", lambda _event: self.load_job())
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

    def new_job(self):
        if self.customer_choice.current() < 0:
            raise ValueError("ابتدا مشتری را انتخاب کنید.")
        customer_id = self.customer_ids[self.customer_choice.current()]
        job_id = create_job(customer_id, self.device_entry.get(), self.problem_entry.get())
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
            self.customer_tree.insert("", "end", values=(c["id"], c["name"], c["phone"], c["address"], c["notes"]))
        for i in items:
            self.item_tree.insert("", "end", values=(
                i["id"], i["sku"] or "", i["name"], i["qty"], money(i["cost"]), money(i["price"])))
        for j in jobs:
            self.job_tree.insert("", "end", values=(
                j["id"], j["order_code"], j["name"], j["device"], j["status"], money(j["labor"]), j["created_at"]))
        self.customer_ids = [c["id"] for c in customers]
        self.customer_choice["values"] = [f"{c['id']} - {c['name']} ({c['phone']})" for c in customers]
        self.item_ids = [i["id"] for i in items]
        self.item_choice["values"] = [
            f"{i['id']} - {i['name']} | موجودی {i['qty']} | {money(i['price'])} تومان" for i in items]


if __name__ == "__main__":
    init_db()
    App().mainloop()
