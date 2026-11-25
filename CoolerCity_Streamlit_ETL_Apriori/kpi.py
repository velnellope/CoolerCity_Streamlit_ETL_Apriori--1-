"""Definisi KPI, target default, dan perhitungan capaian per tahun."""
from dataclasses import dataclass

import pandas as pd

from ui import money, num, pct


@dataclass
class KPI:
    code: str
    name: str
    icon: str
    icon_bg: str
    unit: str            # rupiah | unit | per_day | ratio | lift
    higher_is_better: bool
    yearly: bool         # target berbeda tiap tahun?
    definition: str
    main: bool = True


KPIS = [
    KPI("revenue", "Total Sales Revenue", "💰", "#E2F3FA", "rupiah", True, True,
        "Total akumulasi pendapatan dari seluruh transaksi penjualan."),
    KPI("quantity", "Total Quantity Sold", "🧋", "#E2EDF7", "unit", True, True,
        "Jumlah total unit produk yang terjual kepada pelanggan."),
    KPI("basket", "Average Basket Size", "🧺", "#FDE8EE", "rupiah", True, False,
        "Rata-rata nilai belanja pelanggan per transaksi (omzet ÷ jumlah transaksi)."),
    KPI("peak", "Peak Hours & Days Volume", "⏰", "#FDF3E1", "per_day", True, False,
        "Rata-rata jumlah transaksi per hari pada hari operasional tersibuk, beserta jam tersibuknya."),
    KPI("category_share", "Product Category Share", "🍨", "#EEEBFE", "ratio", True, False,
        "Persentase kontribusi kategori fokus terhadap total penjualan."),
    KPI("lift", "Lift Ratio", "🔗", "#E2F3FA", "lift", True, False,
        "Rata-rata lift aturan asosiasi (Apriori level produk, support ≥5%, confidence ≥50%). Lift > 1 = produk saling mendorong."),
    KPI("growth", "Pertumbuhan Penjualan (YoY)", "📈", "#E2EDF7", "ratio", True, False,
        "Kenaikan omzet dibanding tahun sebelumnya.", main=False),
    KPI("multi_item", "Transaksi Multi-Produk", "🛍️", "#FDE8EE", "ratio", True, False,
        "Persentase transaksi yang berisi ≥2 produk berbeda; ukuran peluang bundling.", main=False),
    KPI("cancel_rate", "Tingkat Pembatalan Order", "⛔", "#FDF3E1", "ratio", False, False,
        "Order dibatalkan ÷ semua order (valid + batal). Semakin kecil semakin baik.", main=False),
]
MAIN_KPIS = [k for k in KPIS if k.main]
BY_CODE = {k.code: k for k in KPIS}
DEFAULT_FOCUS_CATEGORY = "Milk Tea Series"
DEFAULT_TARGETS = {
    (2024, "revenue"): 420_000_000, (2025, "revenue"): 540_000_000,
    (2024, "quantity"): 27_000, (2025, "quantity"): 32_000,
    (0, "basket"): 75_000, (0, "peak"): 24, (0, f"category_share|{DEFAULT_FOCUS_CATEGORY}"): 0.35,
    (0, "lift"): 1.5, (0, "growth"): 0.15, (0, "multi_item"): 0.90, (0, "cancel_rate"): 0.015,
}
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def fmt(unit, v):
    if v is None or pd.isna(v):
        return "–"
    return {"rupiah": lambda x: money(x), "unit": lambda x: num(x) + " unit", "per_day": lambda x: num(x, 1) + " trx/hari",
            "ratio": lambda x: pct(x, 2 if abs(x) < 0.1 else 1), "lift": lambda x: num(x, 2) + "×"}[unit](v)


def target_lookup(targets: pd.DataFrame, year: int):
    """{kpi_code: target} untuk tahun tertentu (target khusus tahun mengalahkan target umum year=0)."""
    out = {}
    if targets is None or targets.empty:
        return out, DEFAULT_FOCUS_CATEGORY
    t = targets.copy()
    t["year"] = t.year.astype(int)
    for y in (0, int(year)):
        for r in t[t.year == y].itertuples():
            out[r.kpi_code] = float(r.target_value)
    focus = DEFAULT_FOCUS_CATEGORY
    for code in list(out):
        if code.startswith("category_share|"):
            focus = code.split("|", 1)[1]
            out["category_share"] = out.pop(code)
    return out, focus


def status_of(k: KPI, actual, target):
    if target is None or actual is None or pd.isna(actual):
        return "none", None
    if k.higher_is_better:
        ach = actual / target if target else 1.0
        return ("ok" if ach >= 1 else "near" if ach >= 0.9 else "miss"), ach
    ach = target / actual if actual else 1.0
    return ("ok" if actual <= target else "near" if actual <= target * 1.1 else "miss"), min(ach, 1.0)


def compute(df_year: pd.DataFrame, df_prev: pd.DataFrame, cancels_year: int, rules: list, focus: str):
    """Nilai aktual + catatan singkat per KPI."""
    orders = df_year.groupby("order_key").agg(total=("line_total", "sum"), n=("sku", "nunique"),
                                              day=("day_name", "first"), date=("full_date", "first"),
                                              hour=("hour", "first"))
    vals, notes = {}, {}
    vals["revenue"] = df_year.line_total.sum()
    notes["revenue"] = f"{num(len(orders))} transaksi"
    vals["quantity"] = df_year.quantity.sum()
    notes["quantity"] = f"≈ {num(vals['quantity'] / max(df_year.full_date.nunique(), 1), 0)} unit/hari"
    vals["basket"] = orders.total.mean() if len(orders) else None
    notes["basket"] = f"Median {money(orders.total.median())}" if len(orders) else ""
    per_day = (orders.groupby("day").size() / orders.groupby("day").date.nunique()).reindex(HARI).dropna()
    if len(per_day):
        top_day = per_day.idxmax()
        hours = orders.hour.value_counts()
        vals["peak"] = per_day.max()
        notes["peak"] = f"Tersibuk: <b>{top_day}</b> · jam <b>{hours.idxmax():02d}.00–{hours.idxmax() + 1:02d}.00</b>"
    share = df_year.groupby("category_name").line_total.sum() / df_year.line_total.sum()
    vals["category_share"] = share.get(focus)
    notes["category_share"] = f"Kategori fokus: <b>{focus}</b>" + (
        f" · terbesar: {share.idxmax()}" if share.idxmax() != focus else " (terbesar)")
    if rules:
        vals["lift"] = sum(r["lift"] for r in rules) / len(rules)
        best = rules[0]
        notes["lift"] = f"{len(rules)} aturan · tertinggi {num(best['lift'], 2)}×"
    else:
        vals["lift"] = None
        notes["lift"] = "Tidak ada aturan pada parameter default"
    if df_prev is not None and not df_prev.empty:
        prev = df_prev.line_total.sum()
        vals["growth"] = vals["revenue"] / prev - 1
        notes["growth"] = f"Tahun lalu {money(prev, short=True)}"
    else:
        vals["growth"] = None
        notes["growth"] = "Tidak ada data tahun sebelumnya"
    vals["multi_item"] = (orders.n > 1).mean() if len(orders) else None
    notes["multi_item"] = f"{num((orders.n > 1).sum())} transaksi berisi ≥2 produk"
    total_orders = len(orders) + cancels_year
    vals["cancel_rate"] = cancels_year / total_orders if total_orders else None
    notes["cancel_rate"] = f"{num(cancels_year)} order dibatalkan"
    return vals, notes, orders


def monthly_vs_target(df_year: pd.DataFrame, annual_target):
    m = df_year.groupby("month").agg(revenue=("line_total", "sum")).reindex(range(1, 13), fill_value=0).reset_index()
    m["target"] = annual_target / 12 if annual_target else None
    return m
