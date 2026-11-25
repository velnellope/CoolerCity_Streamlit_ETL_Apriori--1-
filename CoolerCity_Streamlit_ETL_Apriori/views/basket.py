"""Analisis Apriori dengan bahasa awam: 'Jika membeli A, seberapa besar kemungkinan juga membeli B?'"""
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui
from analytics.apriori import LEVELS

# Kemasan (Cup/Cone) selalu dikeluarkan dan transaksi yang hanya berisi topping selalu diabaikan,
# karena keduanya bukan keputusan belanja menu. Aturan ini tetap, tidak perlu diatur pengguna.
EXCLUDE_PACKAGING = True
DROP_TOPPING_ONLY = True
LEVEL_LABEL = {"Produk (ukuran digabung)": "Per menu (ukuran digabung)",
               "Produk + varian ukuran": "Per menu & ukuran",
               "Kategori": "Per kategori menu"}


def strength(lift):
    if lift >= 3:
        return "Sangat kuat", "#00568E", "#E2F3FA"
    if lift >= 1.5:
        return "Kuat", "#0098C8", "#E8F6FC"
    if lift > 1:
        return "Lemah", "#B7791F", "#FDF3E1"
    return "Tidak ada", "#5F7189", "#EEF1F5"


def controls(df, key):
    """Pilihan analisis + filter transaksi. Mengembalikan hasil Apriori dan parameter."""
    with st.container(border=True):
        c = st.columns([1.3, 1, 1, 1])
        level = c[0].selectbox("Lihat hubungan", list(LEVELS), format_func=LEVEL_LABEL.get, key=key + "lvl",
                               help="Per menu: menu apa dibeli bersama menu apa. Per kategori: kelompok menu apa dibeli bersama.")
        years = sorted(int(y) for y in df.year.unique())
        y = ui.all_or(c[1].pills("Tahun", years, selection_mode="multi", key=key + "y"), years)
        ch_opts = sorted(df.sales_channel.unique())
        ch = ui.all_or(c[2].multiselect("Kanal", ch_opts, key=key + "c", placeholder="Semua kanal"), ch_opts)
        ty_opts = sorted(df.order_type.unique())
        ty = ui.all_or(c[3].multiselect("Tipe order", ty_opts, key=key + "t", placeholder="Semua tipe"), ty_opts)
        with st.expander("⚙️ Pengaturan untuk analis (opsional)"):
            st.caption("Biarkan nilai bawaan bila tidak yakin. Menurunkan angka akan memunculkan lebih banyak pasangan, "
                       "termasuk yang hubungannya lemah.")
            p = st.columns(3)
            sup = p[0].slider("Minimal muncul di … % transaksi (support)", 0.5, 30.0, 5.0, 0.5, key=key + "s")
            conf = p[1].slider("Minimal peluang ikut dibeli, % (confidence)", 5, 100, 50, 5, key=key + "cf")
            lift = p[2].slider("Minimal kekuatan hubungan, × (lift)", 0.5, 5.0, 1.0, 0.1, key=key + "l")
    res = data.rules_for(tuple(sorted(y)), tuple(sorted(ch)), tuple(sorted(ty)), level, EXCLUDE_PACKAGING,
                         DROP_TOPPING_ONLY, sup / 100, conf / 100, lift)
    return res, dict(level=level, sup=sup, conf=conf, lift=lift)


def prepare(rules: pd.DataFrame) -> pd.DataFrame:
    r = rules.copy()
    r["A"] = r.antecedent.apply(" + ".join)
    r["B"] = r.consequent.apply(" + ".join)
    r["baseline"] = r.confidence / r.lift          # peluang B dibeli oleh pelanggan pada umumnya
    r["Kekuatan"] = r.lift.map(lambda x: strength(x)[0])
    return r


CAT_ICON = {"Milk Tea Series": "🧋", "Fruit Tea Series": "🍹", "Ice Cream Series": "🍦", "Yogurt Series": "🥛",
            "Pure Tea Series": "🍵", "Matcha Series": "🍵", "Cocoa Series": "🍫", "Coffee Series": "☕",
            "Smoothies": "🥤", "Promo/Bundling": "🎁", "Topping & Tambahan": "🔸", "Topping": "🔸", "Kemasan": "🥡"}


def icon_for(df, level):
    """Ikon tiap item: dari kategorinya."""
    if level == "Kategori":
        return lambda name: CAT_ICON.get(name, "🍧")
    col = LEVELS[level]
    cat = df.drop_duplicates(col).set_index(col).category_name
    return lambda name: " ".join(CAT_ICON.get(cat.get(n.strip(), ""), "🍧") for n in name.split(" + "))


def pair_tile(r, icon):
    lab, fg, bg = strength(r.lift)
    conf, base = r.confidence * 100, r.baseline * 100
    return f"""
    <div class="rule-card" style="padding:18px">
      <div style="display:flex;align-items:center;gap:10px;justify-content:space-between">
        <div style="text-align:center;flex:1"><div style="font-size:2rem">{icon(r.A)}</div>
          <div style="font-weight:800;color:#0B2D4F;font-size:.9rem;line-height:1.2">{html.escape(r.A)}</div></div>
        <div style="font-size:1.6rem;color:{fg}">➜</div>
        <div style="text-align:center;flex:1"><div style="font-size:2rem">{icon(r.B)}</div>
          <div style="font-weight:800;color:#0B2D4F;font-size:.9rem;line-height:1.2">{html.escape(r.B)}</div></div>
      </div>
      <div style="display:flex;align-items:baseline;gap:8px;margin-top:12px">
        <span style="font-size:2rem;font-weight:900;color:{fg}">{conf:.0f}%</span>
        <span style="color:#5F7189;font-size:.85rem">juga beli</span>
        <span class="tag" style="margin-left:auto;color:{fg};background:{bg}">{lab} · {ui.num(r.lift, 1)}×</span>
      </div>
      <div style="position:relative;height:10px;background:#EEF1F5;border-radius:999px;margin-top:8px">
        <div style="width:{conf:.0f}%;height:100%;background:{fg};border-radius:999px"></div>
        <div title="Pelanggan biasa" style="position:absolute;left:{base:.0f}%;top:-4px;width:3px;height:18px;background:#0B2D4F;border-radius:2px"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.75rem;color:#5F7189;margin-top:6px">
        <span>▮ biasanya {base:.0f}%</span><span>🛒 {ui.num(r.count)} transaksi</span></div>
    </div>"""


def render():
    df = data.require_data()
    ui.page_header("Market Basket", "Analisis Apriori", "Menu apa yang sering dibeli <b>bersamaan</b>?")
    st.markdown("""
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin:-4px 0 14px">
      <span class="tag" style="background:#E2F3FA;color:#00568E;font-size:.85rem;padding:7px 14px">🛒 1 transaksi = 1 keranjang</span>
      <span class="tag" style="background:#FCE4EF;color:#B2457A;font-size:.85rem;padding:7px 14px">🔍 cari menu yang sering sekeranjang</span>
      <span class="tag" style="background:#FFF6D6;color:#8A6A00;font-size:.85rem;padding:7px 14px">➜ jika beli A, sering juga beli B</span>
    </div>""", unsafe_allow_html=True)
    res, p = controls(df, "ap")
    if not res["rules"]:
        st.warning("Belum ada pasangan yang memenuhi syarat. Pilih **Per kategori menu** atau turunkan angka di pengaturan.")
        return
    rules = prepare(pd.DataFrame(res["rules"]))
    icon = icon_for(df, p["level"])
    counts = rules.Kekuatan.value_counts()

    a, b, c = st.columns(3)
    a.metric("🛒 Transaksi dianalisis", ui.num(res["orders"]))
    b.metric("🔗 Pasangan ditemukan", ui.num(len(rules)))
    c.metric("💪 Hubungan terkuat", f"{ui.num(rules.lift.max(), 1)}×",
             help="Berapa kali lebih sering menu B dibeli oleh pembeli menu A dibanding pelanggan biasa.")

    # ---------------- pasangan terkuat (kartu visual)
    ui.section("Pasangan menu terkuat")
    pairs, seen = [], set()
    for r in rules.itertuples():
        key = frozenset(r.antecedent + r.consequent)
        if key not in seen:
            seen.add(key)
            pairs.append(r)
    for i in range(0, min(len(pairs), 6), 3):
        cols = st.columns(3)
        for col, r in zip(cols, pairs[i:i + 3]):
            col.markdown(pair_tile(r, icon), unsafe_allow_html=True)
    st.caption("Angka besar = dari pembeli menu kiri, berapa persen juga membeli menu kanan. "
               "Garis gelap pada bar = persentase pelanggan biasa yang membeli menu kanan.")

    # ---------------- grafik: pelanggan biasa vs pembeli A
    ui.section("Pelanggan biasa vs pembeli menu A")
    top = rules.head(8).iloc[::-1]
    labels = [f"{icon(a_)} {a_}  ➜  {icon(b_)} {b_}" for a_, b_ in zip(top.A, top.B)]
    fig = go.Figure()
    fig.add_bar(y=labels, x=top.baseline * 100, orientation="h", name="Pelanggan biasa",
                marker_color="#C9D6E3", marker_cornerradius=5, text=[ui.pct(v, 0) for v in top.baseline],
                textposition="outside", hovertemplate="Pelanggan biasa membeli menu kanan: %{x:.0f}%<extra></extra>")
    fig.add_bar(y=labels, x=top.confidence * 100, orientation="h", name="Pembeli menu kiri",
                marker_color=ui.TEAL, marker_cornerradius=5,
                text=[f"{ui.pct(v, 0)} · {ui.num(l, 1)}×" for v, l in zip(top.confidence, top.lift)],
                textposition="outside", hovertemplate="Pembeli menu kiri yang juga membeli menu kanan: %{x:.0f}%<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.08)
    fig.update_xaxes(range=[0, 118], ticksuffix="%", title="Peluang membeli menu kanan")
    ui.show(fig, 120 + 62 * len(top))

    # ---------------- semua pasangan: tabel visual
    ui.section("Semua pasangan")
    levels = ["Sangat kuat", "Kuat", "Lemah"]
    c1, c2 = st.columns([1.2, 2])
    with c1:
        pick = st.pills("Kekuatan hubungan", levels, selection_mode="multi",
                        default=[l for l in levels if counts.get(l, 0)], key="ap_strength") or levels
    with c2:
        st.markdown("".join(
            f'<span class="tag" style="color:{strength(v)[1]};background:{strength(v)[2]};font-size:.85rem;padding:6px 14px;'
            f'margin:26px 8px 0 0">{lab} ({rng}): {int(counts.get(lab, 0))}</span>'
            for lab, v, rng in (("Sangat kuat", 3, "≥3×"), ("Kuat", 1.5, "1,5–3×"), ("Lemah", 1.01, "1–1,5×"))),
            unsafe_allow_html=True)
    if counts.get("Kuat", 0) + counts.get("Lemah", 0) == 0:
        st.caption("💡 Hubungan kuat/lemah muncul jika memilih **Per kategori menu** atau menurunkan angka di pengaturan.")
    shown = rules[rules.Kekuatan.isin(pick)]
    stars = {"Sangat kuat": "★★★", "Kuat": "★★☆", "Lemah": "★☆☆"}
    table = pd.DataFrame({
        "Jika beli": [f"{icon(x)} {x}" for x in shown.A], "Juga beli": [f"{icon(x)} {x}" for x in shown.B],
        "Peluang ikut dibeli": (shown.confidence * 100).round(1), "Biasanya": (shown.baseline * 100).round(1),
        "Lebih sering": shown.lift.round(2), "Kekuatan": shown.Kekuatan.map(lambda k: f"{stars[k]} {k}"),
        "Transaksi": shown["count"]})
    st.dataframe(table, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(table)), column_config={
        "Peluang ikut dibeli": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        "Biasanya": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        "Lebih sering": st.column_config.NumberColumn(format="%.1f×")})
    st.download_button("Unduh tabel (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                       file_name="coolercity_aturan_asosiasi.csv", mime="text/csv", icon=":material/download:")

    with st.expander("📚 Istilah teknis (untuk laporan)"):
        st.markdown(f"""
| Istilah | Di dashboard | Rumus |
|---|---|---|
| **Support** | Muncul di … % transaksi | transaksi berisi A dan B ÷ semua transaksi |
| **Confidence** | Peluang ikut dibeli | transaksi A dan B ÷ transaksi berisi A |
| **Lift** | Lebih sering (×) | confidence ÷ support(B) = peluang ikut dibeli ÷ biasanya |

Parameter: support ≥ {p['sup']:g}% · confidence ≥ {p['conf']:g}% · lift ≥ {p['lift']:g} · maksimal 3 item.
Kemasan (Cup/Cone) tidak dihitung sebagai menu; transaksi yang hanya berisi topping diabaikan.
""")
