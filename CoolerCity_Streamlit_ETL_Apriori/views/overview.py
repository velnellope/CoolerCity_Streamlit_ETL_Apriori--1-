import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import kpi
import ui

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def render():
    df = data.require_data()
    years = sorted(int(y) for y in df.year.unique())
    ui.page_header("Dashboard", "Ringkasan KPI",
                   "Capaian indikator kinerja utama dibandingkan target. Pilih tahun untuk melihat kinerjanya.")
    year = st.segmented_control("Tahun", years, default=years[-1], key="ov_year") or years[-1]

    targets, focus = kpi.target_lookup(_safe(data.targets, pd.DataFrame()), year)
    dfy, dfp = df[df.year == year], df[df.year == year - 1]
    canc = _safe(data.cancellations, pd.DataFrame())
    n_cancel = int((canc.order_datetime.dt.year == year).sum()) if not canc.empty else 0
    channels = tuple(sorted(df.sales_channel.unique()))
    types = tuple(sorted(df.order_type.unique()))
    rules = data.rules_for((year,), channels, types, "Produk (ukuran digabung)", True, True, 0.05, 0.5, 1.0)["rules"]
    vals, notes, orders = kpi.compute(dfy, dfp, n_cancel, rules, focus)

    cards, statuses = {}, {}
    for k in kpi.MAIN_KPIS:
        status, ach = kpi.status_of(k, vals.get(k.code), targets.get(k.code))
        statuses[k.code] = status
        tgt = targets.get(k.code)
        tgt_text = (("≤ " if not k.higher_is_better else "≥ " if k.unit in ("ratio", "lift", "per_day") else "")
                    + kpi.fmt(k.unit, tgt)) if tgt is not None else None
        cards[k.code] = ui.kpi_card(k.name, k.icon, k.icon_bg, kpi.fmt(k.unit, vals.get(k.code)), status, ach, tgt_text,
                                    notes.get(k.code, ""), k.definition)

    rated = [s for s in statuses.values() if s != "none"]
    ok = sum(s == "ok" for s in rated)
    near = sum(s == "near" for s in rated)
    miss = sum(s == "miss" for s in rated)
    st.markdown(f'<div class="summary"><div><div style="font-size:.8rem;color:#D4EEFA;font-weight:700">STATUS TARGET {year}</div>'
                f'<div class="big">{ok} dari {len(rated)} KPI tercapai</div></div><div style="flex:1"></div>'
                f'<span class="chip">✅ {ok} tercapai</span><span class="chip">🟡 {near} hampir</span>'
                f'<span class="chip">🔴 {miss} belum</span></div>', unsafe_allow_html=True)

    ui.section("KPI Utama", "Enam indikator yang dipantau manajemen. Bar menunjukkan persentase capaian target.")
    ui.card_grid([cards[k.code] for k in kpi.MAIN_KPIS], 3)

    ui.section("Penjualan Bulanan vs Target", "Target bulanan = target tahunan ÷ 12.")
    m = kpi.monthly_vs_target(dfy, targets.get("revenue"))
    colors = [ui.TEAL if (m.target.isna().all() or r >= t) else ui.BERRY for r, t in zip(m.revenue, m.target.fillna(0))]
    fig = go.Figure()
    fig.add_bar(x=BULAN, y=m.revenue, marker_color=colors, name="Penjualan", marker_cornerradius=6,
                hovertemplate="%{x}: Rp%{y:,.0f}<extra></extra>")
    if m.target.notna().all():
        fig.add_scatter(x=BULAN, y=m.target, mode="lines", name="Target bulanan",
                        line=dict(color=ui.INK, dash="dash", width=2), hovertemplate="Target: Rp%{y:,.0f}<extra></extra>")
    fig.update_yaxes(tickformat=",.0f", title="Rupiah", tickprefix="Rp")
    ui.show(fig, 360)
    if m.target.notna().all():
        below = [BULAN[i] for i, (r, t) in enumerate(zip(m.revenue, m.target)) if r < t and r > 0]
        ui.howto("Batang <b style='color:#0098C8'>hijau</b> = bulan yang mencapai target bulanan, "
                 "<b style='color:#E0679C'>merah muda</b> = di bawah target. Garis putus-putus = target.")
    best_m, worst_m = m.revenue.idxmax(), m.revenue[m.revenue > 0].idxmin()
    top_cat = dfy.groupby("category_name").line_total.sum().idxmax()
    pts = [
        f"Bulan terbaik <b>{BULAN[best_m]}</b> ({ui.money(m.revenue[best_m], True)}), terendah <b>{BULAN[worst_m]}</b> "
        f"({ui.money(m.revenue[worst_m], True)}).",
        (f"{len(below)} bulan di bawah target: {', '.join(below)}." if m.target.notna().all() and below else
         "Semua bulan mencapai target bulanan." if m.target.notna().all() else
         "Target penjualan tahun ini belum diatur — Admin dapat mengisinya di menu Target KPI."),
        f"Kategori dengan kontribusi terbesar: <b>{top_cat}</b>.",
        (f"Pasangan produk terkuat: <b>{' + '.join(rules[0]['antecedent'])} → {' + '.join(rules[0]['consequent'])}</b> "
         f"(lift {ui.num(rules[0]['lift'], 2)}×), kandidat paket bundling." if rules else ""),
    ]
    miss_names = [k.name for k in kpi.MAIN_KPIS if statuses[k.code] in ("miss", "near")]
    if miss_names:
        pts.append("Perlu perhatian: " + ", ".join(f"<b>{n}</b>" for n in miss_names) + ".")
    ui.insight(pts, f"Ringkasan {year}")
    st.caption("Target dapat diubah Admin di menu **Kelola Data → Target KPI**. Status: ✅ ≥100% target · "
               "🟡 90–99% · 🔴 <90%.")
