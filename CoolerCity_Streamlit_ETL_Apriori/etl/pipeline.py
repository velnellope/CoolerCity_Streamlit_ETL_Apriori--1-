"""ETL CoolerCity: export mentah POS + GoFood/GrabFood/ShopeeFood + Daftar Menu -> Star Schema.

Extract   : setiap file dibaca sebagai teks (dtype=str) agar ID panjang tidak berubah ke notasi ilmiah.
Transform : adapter per sumber -> format staging seragam -> validasi -> mapping SKU -> deduplikasi
            -> surrogate key -> tabel dimensi & fakta.
Load      : ditangani load_warehouse() dalam satu transaksi SQL Server (lihat bawah).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

POS_SHEET = "Laporan Penjualan per Item"
MENU_SHEET = "Daftar Menu"
OJOL_SHEETS = ("GoFood", "GrabFood", "ShopeeFood")
VALID_STATUS = {"selesai", "completed"}
CANCEL_STATUS = {"dibatalkan", "cancelled", "canceled", "batal", "refund", "refunded"}
PAYMENT_POS = {"tunai": "Cash", "cash": "Cash", "qris": "QRIS", "qris bca": "QRIS",
               "kartu debit": "Debit Card", "debit": "Debit Card", "debit card": "Debit Card"}
SOURCE_CODE = {"POS Outlet": "POS", "GoFood": "GOF", "GrabFood": "GRB", "ShopeeFood": "SPF"}
NON_MENU_CATEGORIES = {"Kemasan"}
STAGING_COLS = ["source", "file_name", "source_row", "source_order_id", "order_datetime_raw", "order_datetime",
                "order_type", "customer_name_raw", "sku_raw", "item_name_raw", "variant_raw", "quantity",
                "unit_price", "line_total", "payment_method", "status_raw"]


@dataclass
class ETLResult:
    staging: pd.DataFrame
    rejected: pd.DataFrame
    clean: pd.DataFrame
    dims: dict = field(default_factory=dict)
    fact: pd.DataFrame | None = None
    summary: pd.DataFrame | None = None
    stats: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------- helpers
def _norm(text) -> str:
    """Normalise a product name for matching: lower case, single spaces, no stray punctuation spacing."""
    s = str(text or "").lower().strip()
    s = re.sub(r"\(\s*", "(", s)
    s = re.sub(r"\s*\)", ")", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    return re.sub(r"\s+", " ", s)


def _number(series: pd.Series) -> pd.Series:
    """Parse '20000', '20.000' (format Indonesia), '20,000.00' (format Grab), 'Rp20.000'."""
    s = series.astype("string").str.strip().str.replace(r"(?i)rp|\s", "", regex=True)
    grab = s.str.contains(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$", na=False)
    indo = s.str.contains(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$", na=False)
    s = s.mask(grab, s.str.replace(",", "", regex=False))
    s = s.mask(indo, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def _read(file_name: str, data: bytes) -> dict[str, pd.DataFrame]:
    if file_name.lower().endswith(".csv"):
        return {"csv": pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)}
    book = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, keep_default_na=False)
    return {name: df.rename(columns=lambda c: str(c).strip()) for name, df in book.items()}


def _require(df: pd.DataFrame, cols: list[str], where: str):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{where}: kolom wajib tidak ditemukan: {', '.join(missing)}")


def _frame(df: pd.DataFrame, file_name: str, **cols) -> pd.DataFrame:
    out = pd.DataFrame({k: (v if isinstance(v, pd.Series) else pd.Series(v, index=df.index)) for k, v in cols.items()})
    out["file_name"] = file_name
    out["source_row"] = df.index + 2  # +2 = baris Excel (header di baris 1)
    return out


# ---------------------------------------------------------------- source adapters
def _adapt_pos(df, file_name):
    _require(df, ["Tanggal", "No. Struk", "Tipe Order", "Pelanggan", "SKU", "Nama Menu", "Varian", "Qty",
                  "Harga Satuan", "Total", "Metode Pembayaran", "Status"], f"{file_name} / {POS_SHEET}")
    df = df[df["Tanggal"].str.strip().str.upper() != "TOTAL"]
    return _frame(df, file_name, source="POS Outlet", source_order_id=df["No. Struk"].str.strip(),
                  order_datetime_raw=df["Tanggal"],
                  order_datetime=pd.to_datetime(df["Tanggal"].str.strip(), format="%d/%m/%Y %H:%M", errors="coerce"),
                  order_type=df["Tipe Order"].str.strip().str.title(), customer_name_raw=df["Pelanggan"],
                  sku_raw=df["SKU"].str.strip().str.upper(), item_name_raw=df["Nama Menu"], variant_raw=df["Varian"],
                  quantity=_number(df["Qty"]), unit_price=_number(df["Harga Satuan"]), line_total=_number(df["Total"]),
                  payment_method=df["Metode Pembayaran"].str.strip().str.lower().map(PAYMENT_POS),
                  status_raw=df["Status"])


def _adapt_gofood(df, file_name):
    _require(df, ["Order ID", "Waktu Pesanan", "Nama Customer", "Menu", "Jumlah", "Harga", "Total", "Status"],
             f"{file_name} / GoFood")
    return _frame(df, file_name, source="GoFood", source_order_id=df["Order ID"].str.strip(),
                  order_datetime_raw=df["Waktu Pesanan"],
                  order_datetime=pd.to_datetime(df["Waktu Pesanan"].str.strip(), format="%Y-%m-%dT%H:%M:%S", errors="coerce"),
                  order_type="Delivery", customer_name_raw=df["Nama Customer"], sku_raw="", item_name_raw=df["Menu"],
                  variant_raw="", quantity=_number(df["Jumlah"]), unit_price=_number(df["Harga"]),
                  line_total=_number(df["Total"]), payment_method="GoFood", status_raw=df["Status"])


def _adapt_grabfood(df, file_name):
    _require(df, ["Booking ID", "Created On", "Eater Name", "Item Name", "Quantity", "Item Price", "Status"],
             f"{file_name} / GrabFood")
    qty, price = _number(df["Quantity"]), _number(df["Item Price"])
    return _frame(df, file_name, source="GrabFood", source_order_id=df["Booking ID"].str.strip(),
                  order_datetime_raw=df["Created On"],
                  order_datetime=pd.to_datetime(df["Created On"].str.strip(), format="%d %b %Y %I:%M %p", errors="coerce"),
                  order_type="Delivery", customer_name_raw=df["Eater Name"], sku_raw="", item_name_raw=df["Item Name"],
                  variant_raw="", quantity=qty, unit_price=price, line_total=qty * price, payment_method="GrabFood",
                  status_raw=df["Status"])


def _adapt_shopeefood(df, file_name):
    _require(df, ["No. Pesanan", "Tanggal", "Jam", "Nama Produk", "Qty", "Harga Satuan", "Subtotal", "Status Pesanan"],
             f"{file_name} / ShopeeFood")
    raw_dt = df["Tanggal"].str.strip() + " " + df["Jam"].str.strip()
    return _frame(df, file_name, source="ShopeeFood", source_order_id=df["No. Pesanan"].str.strip(),
                  order_datetime_raw=raw_dt,
                  order_datetime=pd.to_datetime(raw_dt, format="%d-%m-%Y %H:%M:%S", errors="coerce"),
                  order_type="Delivery", customer_name_raw="", sku_raw="", item_name_raw=df["Nama Produk"],
                  variant_raw="", quantity=_number(df["Qty"]), unit_price=_number(df["Harga Satuan"]),
                  line_total=_number(df["Subtotal"]), payment_method="ShopeeFood", status_raw=df["Status Pesanan"])


ADAPTERS = {"GoFood": _adapt_gofood, "GrabFood": _adapt_grabfood, "ShopeeFood": _adapt_shopeefood}


# ---------------------------------------------------------------- extract
def extract(files: list[tuple[str, bytes]]):
    """Detect each uploaded sheet by its name and return (menu, staging, notes)."""
    menu, parts, notes = None, [], []
    for file_name, data in files:
        for sheet, df in _read(file_name, data).items():
            if sheet == MENU_SHEET or {"SKU", "Nama Menu", "Kategori", "Harga"} <= set(df.columns) and "Qty" not in df.columns:
                menu = df.copy()
                notes.append(f"{file_name} / {sheet}: Daftar Menu ({len(df):,} produk)")
            elif sheet == POS_SHEET or {"No. Struk", "Nama Menu", "Qty"} <= set(df.columns):
                parts.append(_adapt_pos(df, file_name))
                notes.append(f"{file_name} / {sheet}: POS Outlet ({len(df):,} baris)")
            elif sheet in ADAPTERS:
                parts.append(ADAPTERS[sheet](df, file_name))
                notes.append(f"{file_name} / {sheet}: {sheet} ({len(df):,} baris)")
            else:
                notes.append(f"{file_name} / {sheet}: dilewati (format tidak dikenali)")
    if menu is None:
        raise ValueError("Daftar Menu belum di-upload. File ini wajib karena menjadi acuan SKU, kategori dan harga.")
    if not parts:
        raise ValueError("Belum ada file transaksi (POS atau Ojol) yang dikenali.")
    staging = pd.concat(parts, ignore_index=True)[STAGING_COLS]
    return menu, staging, notes


# ---------------------------------------------------------------- transform
def _prepare_menu(menu: pd.DataFrame) -> pd.DataFrame:
    _require(menu, ["SKU", "Kategori", "Nama Menu", "Varian", "Harga"], "Daftar Menu")
    m = menu.copy()
    m["SKU"] = m["SKU"].str.strip().str.upper()
    m["Nama Menu"] = m["Nama Menu"].str.strip()
    m["Varian"] = m["Varian"].str.strip().replace({"": "-"})
    m["Harga"] = _number(m["Harga"])
    if m["SKU"].duplicated().any():
        raise ValueError("Daftar Menu: SKU ganda: " + ", ".join(m.loc[m.SKU.duplicated(), "SKU"].unique()[:10]))
    m["product_name"] = m["Nama Menu"] + m["Varian"].map(lambda v: "" if v == "-" else f" - {v}")
    return m


def _menu_lookup(m: pd.DataFrame) -> dict[str, str]:
    """All name spellings seen in the exports -> SKU."""
    short = {"Medium": "M", "Large": "L", "Regular": "R", "Small": "S"}
    look = {}
    for r in m.to_dict("records"):
        base, var = r["Nama Menu"], r["Varian"]
        sv = short.get(var, var)
        names = {base} if var == "-" else {f"{base} - {var}", f"{base} {var}", f"{base} ({var})", f"{base} ({sv})",
                                           f"{base} - {sv}"}
        for n in names:
            look.setdefault(_norm(n), r["SKU"])
    return look


def _clean_customer(stg: pd.DataFrame) -> pd.Series:
    name = stg["customer_name_raw"].fillna("").str.strip()
    masked = name.str.contains(r"\*", regex=True)
    out = name.str.title()
    out = out.mask(stg.source.ne("POS Outlet") & (masked | name.eq("")), "Pelanggan " + stg.source)
    out = out.mask(stg.source.ne("POS Outlet") & ~masked & name.ne(""), name.str.title() + " (" + stg.source + ")")
    pos = stg.source.eq("POS Outlet")
    out = out.mask(pos & name.eq(""), "Walk-in (tidak tercatat)")
    # POS: nama depan saja -> nama lengkap bila hanya ada SATU nama lengkap dengan nama depan tsb.
    full = pd.Series(out[pos & out.str.contains(" ") & ~out.str.startswith("Walk-in")].unique())
    first_to_full = full.groupby(full.str.split().str[0]).agg(lambda s: s.iloc[0] if len(s) == 1 else None).dropna()
    single = pos & ~out.str.contains(" ")
    return out.mask(single & out.isin(first_to_full.index), out.map(first_to_full))


def transform(menu_raw: pd.DataFrame, staging: pd.DataFrame) -> ETLResult:
    m = _prepare_menu(menu_raw)
    look = _menu_lookup(m)
    stg = staging.copy()
    stg["status"] = stg["status_raw"].str.strip().str.lower()
    reason = pd.Series("", index=stg.index, dtype="object")

    def reject(mask, text):
        nonlocal reason
        reason = reason.mask(mask & reason.eq(""), text)

    reject(stg.status.isin(CANCEL_STATUS), "Transaksi dibatalkan")
    reject(~stg.status.isin(VALID_STATUS | CANCEL_STATUS), "Status tidak dikenali")
    reject(stg.source_order_id.fillna("").eq(""), "Nomor order kosong")
    reject(stg.order_datetime.isna(), "Format tanggal/jam tidak valid")
    reject(stg.quantity.isna() | (stg.quantity <= 0), "Qty kosong / tidak valid")
    reject(stg.unit_price.isna() | (stg.unit_price < 0), "Harga kosong / tidak valid")
    reject(stg.payment_method.isna(), "Metode pembayaran tidak dikenali")

    # SKU: POS pakai kolom SKU, fallback nama+varian; ojol pakai nama menu
    by_sku = stg.sku_raw.where(stg.sku_raw.isin(set(m.SKU)))
    name_key = (stg.item_name_raw.fillna("") + stg.variant_raw.fillna("").map(
        lambda v: "" if v.strip() in ("", "-") else f" - {v.strip()}")).map(_norm)
    stg["sku"] = by_sku.fillna(name_key.map(look))
    reject(stg.sku.isna(), "Produk tidak ada di Daftar Menu")

    # duplikat persis (glitch export): baris kedua dst. ditolak
    dup_cols = ["source", "source_order_id", "order_datetime_raw", "sku", "quantity", "unit_price", "line_total"]
    reject(stg.duplicated(dup_cols, keep="first") & reason.eq(""), "Baris duplikat")
    stg["reject_reason"] = reason

    rejected = stg[reason.ne("")].copy()
    ok = stg[reason.eq("")].copy()

    # konsistensi harga dengan Daftar Menu (dicatat sebagai peringatan, tidak ditolak)
    warnings = []
    menu_price = ok.sku.map(dict(zip(m.SKU, m.Harga)))
    diff = (ok.unit_price != menu_price).sum()
    if diff:
        warnings.append(f"{diff:,} baris memiliki harga berbeda dari Daftar Menu (harga transaksi tetap dipakai).")
    calc = (ok.quantity * ok.unit_price - ok.line_total).abs() > 0.5
    if calc.any():
        warnings.append(f"{int(calc.sum()):,} baris: Total ≠ Qty × Harga (kemungkinan diskon); nilai Total dipakai.")
    # satu order harus punya satu waktu & satu metode bayar
    hdr_conflict = ok.groupby(["source", "source_order_id"]).agg(t=("order_datetime", "nunique"), p=("payment_method", "nunique"))
    if (hdr_conflict.max(axis=1) > 1).any():
        warnings.append(f"{int((hdr_conflict.max(axis=1) > 1).sum())} order punya waktu/metode bayar berbeda antarbaris.")

    ok["order_key"] = ok.source.map(SOURCE_CODE) + "-" + ok.source_order_id
    ok["customer_name"] = _clean_customer(ok)
    ok["sales_channel"] = ok.source.replace({"POS Outlet": "Offline (Outlet)"})
    ok["channel_type"] = ok.source.map(lambda s: "Offline" if s == "POS Outlet" else "Online Delivery")
    ok = ok.merge(m[["SKU", "product_name", "Nama Menu", "Varian", "Kategori"]], left_on="sku", right_on="SKU", how="left")
    ok = ok.rename(columns={"Nama Menu": "base_product", "Varian": "variant", "Kategori": "category_name"})

    res = ETLResult(staging=stg, rejected=rejected, clean=ok, warnings=warnings)
    _build_star(res, m)
    _summarise(res)
    return res


def _build_star(res: ETLResult, m: pd.DataFrame):
    ok = res.clean
    # dim_date: kalender penuh (termasuk hari tanpa transaksi)
    days = pd.date_range(ok.order_datetime.min().normalize().replace(month=1, day=1),
                         ok.order_datetime.max().normalize().replace(month=12, day=31), freq="D")
    hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
             "November", "Desember"]
    dim_date = pd.DataFrame({"date_key": days.strftime("%Y%m%d").astype(int), "full_date": days.date,
                             "day_of_month": days.day, "day_name": [hari[d] for d in days.dayofweek],
                             "day_of_week": days.dayofweek + 1, "is_weekend": (days.dayofweek >= 5).astype(int),
                             "month": days.month, "month_name": [bulan[x - 1] for x in days.month],
                             "quarter": "Q" + days.quarter.astype(str), "year": days.year})
    # dim_time: per menit
    mins = pd.Series(range(24 * 60))
    period = pd.cut(mins // 60, [-1, 10, 14, 17, 23], labels=["Pagi", "Siang", "Sore", "Malam"]).astype(str)
    dim_time = pd.DataFrame({"time_key": (mins // 60) * 100 + mins % 60, "hour": mins // 60, "minute": mins % 60,
                             "time_label": (mins // 60).map("{:02d}".format) + ":" + (mins % 60).map("{:02d}".format),
                             "day_period": period})
    # dim_product: surrogate key berurutan SKU (seluruh Daftar Menu)
    dim_product = m.sort_values("SKU").reset_index(drop=True)
    dim_product = pd.DataFrame({"sk_product": dim_product.index + 1, "sku": dim_product.SKU,
                                "product_name": dim_product.product_name, "base_product": dim_product["Nama Menu"],
                                "variant": dim_product.Varian, "category_name": dim_product.Kategori,
                                "list_price": dim_product.Harga,
                                "is_menu_item": (~dim_product.Kategori.isin(NON_MENU_CATEGORIES)).astype(int)})

    def small_dim(col, sk, extra=None):
        vals = ok[[col] + (extra or [])].drop_duplicates(col).sort_values(col).reset_index(drop=True)
        vals.insert(0, sk, vals.index + 1)
        return vals

    dim_channel = small_dim("sales_channel", "sk_channel", ["channel_type"])
    dim_payment = small_dim("payment_method", "sk_payment")
    dim_order_type = small_dim("order_type", "sk_order_type")
    cust = ok[["customer_name", "source"]].drop_duplicates("customer_name").sort_values("customer_name").reset_index(drop=True)
    cust["customer_segment"] = cust.apply(
        lambda r: "Walk-in" if r.customer_name.startswith("Walk-in") else
        ("Pelanggan Ojol" if r.source != "POS Outlet" else "Member Outlet"), axis=1)
    dim_customer = cust[["customer_name", "customer_segment"]]
    dim_customer.insert(0, "sk_customer", dim_customer.index + 1)

    f = ok.copy()
    f["date_key"] = f.order_datetime.dt.strftime("%Y%m%d").astype(int)
    f["time_key"] = f.order_datetime.dt.hour * 100 + f.order_datetime.dt.minute
    f = (f.merge(dim_product[["sk_product", "sku"]], on="sku")
          .merge(dim_channel[["sk_channel", "sales_channel"]], on="sales_channel")
          .merge(dim_payment, on="payment_method").merge(dim_order_type, on="order_type")
          .merge(dim_customer[["sk_customer", "customer_name"]], on="customer_name"))
    f = f.sort_values(["order_datetime", "order_key", "sku"]).reset_index(drop=True)
    f["line_no"] = f.groupby("order_key").cumcount() + 1
    fact = f[["order_key", "line_no", "source", "source_order_id", "date_key", "time_key", "sk_product", "sk_channel",
              "sk_payment", "sk_order_type", "sk_customer", "quantity", "unit_price", "line_total"]].copy()
    fact["quantity"] = fact.quantity.astype(int)
    assert len(fact) == len(ok), "Ada baris hilang saat membentuk tabel fakta"
    res.fact = fact
    res.dims = {"dim_date": dim_date, "dim_time": dim_time, "dim_product": dim_product, "dim_channel": dim_channel,
                "dim_payment": dim_payment, "dim_order_type": dim_order_type, "dim_customer": dim_customer}


def _summarise(res: ETLResult):
    stg, ok, rej = res.staging, res.clean, res.rejected
    rows = []
    for src in stg.source.unique():
        s, o, r = stg[stg.source == src], ok[ok.source == src], rej[rej.source == src]
        rows.append({"Sumber": src, "Baris mentah": len(s), "Baris valid": len(o), "Baris ditolak": len(r),
                     "Transaksi valid": o.source_order_id.nunique(), "Omzet (Rp)": float(o.line_total.sum())})
    summary = pd.DataFrame(rows)
    total = summary.sum(numeric_only=True).to_dict()
    total["Sumber"] = "TOTAL"
    res.summary = pd.concat([summary, pd.DataFrame([total])], ignore_index=True)
    res.stats = {"raw_rows": int(len(stg)), "valid_rows": int(len(ok)), "rejected_rows": int(len(rej)),
                 "unique_orders": int(ok.order_key.nunique()), "revenue": float(ok.line_total.sum()),
                 "rejected_by_reason": rej.reject_reason.value_counts().to_dict(),
                 "period": f"{ok.order_datetime.min():%Y-%m-%d} s.d. {ok.order_datetime.max():%Y-%m-%d}"}


def run_etl(files: list[tuple[str, bytes]]) -> tuple[ETLResult, list[str]]:
    menu, staging, notes = extract(files)
    res = transform(menu, staging)
    if res.fact is None or res.fact.empty:
        raise ValueError("Tidak ada transaksi valid setelah validasi.")
    return res, notes


# ---------------------------------------------------------------- load
DIM_ORDER = ["dim_date", "dim_time", "dim_product", "dim_channel", "dim_payment", "dim_order_type", "dim_customer"]


def _py(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v.item() if hasattr(v, "item") else v


def _insert(cur, table, df, chunk=5000):
    cols = list(df.columns)
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})"
    if hasattr(cur, "fast_executemany"):
        cur.fast_executemany = True
    data = [tuple(_py(v) for v in rec) for rec in df.itertuples(index=False, name=None)]
    for i in range(0, len(data), chunk):
        cur.executemany(sql, data[i:i + chunk])


def load_warehouse(conn, res: ETLResult, file_names: list[str], schema: str = "cc"):
    """Full refresh dalam SATU transaksi: kalau satu langkah gagal, seluruh isi lama tetap utuh (rollback)."""
    cur = conn.cursor()
    for t in ["fact_sales", *reversed(DIM_ORDER), "stg_sales"]:
        cur.execute(f"DELETE FROM {schema}.{t}")
    stg = res.staging.copy()
    stg = stg[["source", "file_name", "source_row", "source_order_id", "order_datetime_raw", "order_datetime",
               "order_type", "customer_name_raw", "sku_raw", "item_name_raw", "variant_raw", "quantity", "unit_price",
               "line_total", "payment_method", "status_raw", "sku", "reject_reason"]]
    stg["order_datetime"] = stg.order_datetime.astype(object).where(stg.order_datetime.notna(), None)
    stg = stg.astype(object).where(stg.notna(), None)
    _insert(cur, f"{schema}.stg_sales", stg)
    for name in DIM_ORDER:
        _insert(cur, f"{schema}.{name}", res.dims[name])
    _insert(cur, f"{schema}.fact_sales", res.fact)
    s = res.stats
    cur.execute(f"INSERT INTO {schema}.etl_log (run_at, source_files, raw_rows, valid_rows, rejected_rows, orders, revenue, notes) "
                "VALUES (SYSDATETIME(), ?, ?, ?, ?, ?, ?, ?)",
                (", ".join(file_names)[:1000], s["raw_rows"], s["valid_rows"], s["rejected_rows"], s["unique_orders"],
                 s["revenue"], "; ".join(f"{k}: {v}" for k, v in s["rejected_by_reason"].items())[:1000]))
    conn.commit()
