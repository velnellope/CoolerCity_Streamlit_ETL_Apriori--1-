import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data
import ui
from kpi import HARI

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
                 "November", "Desember"]


def filters(df, key, category=True):
    """Filter transaksi. Kotak yang dikosongkan berarti 'semua'."""
    with st.container(border=True):
        cols = st.columns(4 if category else 3)
        years = sorted(int(v) for v in df.year.unique())
        y = ui.all_or(cols[0].pills("Tahun", years, selection_mode="multi", key=key + "y"), years)
        ch_opts = sorted(df.sales_channel.unique())
        ch = ui.all_or(cols[1].multiselect("Kanal penjualan", ch_opts, key=key + "c", placeholder="Semua kanal"), ch_opts)
        ty_opts = sorted(df.order_type.unique())
        ty = ui.all_or(cols[2].multiselect("Tipe order", ty_opts, key=key + "t", placeholder="Semua tipe"), ty_opts)
        out = df[df.year.isin(y) & df.sales_channel.isin(ch) & df.order_type.isin(ty)]
        if category:
            cat_opts = sorted(df.category_name.unique())
            cat = ui.all_or(cols[3].multiselect("Kategori", cat_opts, key=key + "k", placeholder="Semua kategori"), cat_opts)
            out = out[out.category_name.isin(cat)]
        st.caption("Kosongkan pilihan untuk menampilkan semua data.")
    return out.copy(), (tuple(sorted(y)), tuple(sorted(ch)), tuple(sorted(ty)))


def render():
    df = data.require_data()
    ui.page_header("Dashboard", "Analisis Penjualan",
                   "Lihat dari mana penjualan berasal: kapan, lewat kanal apa, dan produk apa yang paling laku.")
    df, _ = filters(df, "sales")
    if df.empty:
        st.warning("Tidak ada data untuk filter ini.")
        return
    orders = df.groupby("order_key").agg(total=("line_total", "sum"), day=("day_name", "first"), hour=("hour", "first"),
                                         date=("full_date", "first"), channel=("sales_channel", "first"))
    a, b, c, d = st.columns(4)
    a.metric("Total penjualan", ui.money(df.line_total.sum(), short=True), help="Jumlah seluruh nilai transaksi valid.")
    b.metric("Jumlah transaksi", ui.num(len(orders)))
    c.metric("Rata-rata per transaksi", ui.money(orders.total.mean()))
    d.metric("Unit terjual", ui.num(df.quantity.sum()))

    t1, t2, t3, t4 = st.tabs(["📈 Tren", "⏰ Waktu sibuk", "🍨 Produk & kategori", "🛵 Kanal & pembayaran"])
    with t1:
        monthly = (df.assign(p=df.full_date.dt.to_period("M")).groupby(["p", "sales_channel"], as_index=False)
                     .line_total.sum().sort_values("p"))
        monthly["bulan"] = monthly.p.map(lambda x: f"{BULAN[x.month - 1]} {str(x.year)[2:]}")
        fig = px.bar(monthly, x="bulan", y="line_total", color="sales_channel", color_discrete_map=ui.CHANNEL_COLORS,
                     labels={"bulan": "", "line_total": "Penjualan (Rp)", "sales_channel": "Kanal"},
                     category_orders={"bulan": list(dict.fromkeys(monthly.bulan))})
        fig.update_traces(marker_cornerradius=4)
        fig.update_yaxes(tickformat=",.0f")
        ui.show(fig, 380, "Penjualan bulanan per kanal")
        ui.howto("Tinggi batang = total penjualan sebulan; warna = kanal. Bandingkan tinggi batang antarbulan untuk melihat musim ramai/sepi.")
        mon = df.groupby(df.full_date.dt.to_period("M")).line_total.sum()
        lbl = lambda x: f"{BULAN_PANJANG[x.month - 1]} {x.year}"  # noqa: E731
        ui.insight([f"Bulan tertinggi: <b>{lbl(mon.idxmax())}</b> ({ui.money(mon.max(), True)}); "
                    f"terendah: <b>{lbl(mon.idxmin())}</b> ({ui.money(mon.min(), True)})."])
    with t2:
        heat = orders.pivot_table(index="day", columns="hour", values="total", aggfunc="count", fill_value=0).reindex(HARI)
        days_count = orders.groupby("day").date.nunique().reindex(HARI)
        avg = heat.div(days_count, axis=0).round(2)
        fig = go.Figure(go.Heatmap(z=avg.values, x=[f"{h:02d}.00" for h in avg.columns], y=avg.index,
                                   colorscale=[[0, "#EEF8FC"], [0.5, "#7CCDEB"], [1, "#0B2D4F"]],
                                   hovertemplate="%{y} jam %{x}: %{z} transaksi rata-rata/hari<extra></extra>",
                                   colorbar=dict(title="trx/hari", thickness=12)))
        ui.show(fig, 360, "Rata-rata transaksi per hari menurut hari & jam", legend=False)
        ui.howto("Semakin gelap kotaknya, semakin ramai. Gunakan untuk menentukan jadwal staf dan jam promo.")
        per_day = (orders.groupby("day").size() / days_count).reindex(HARI)
        hours = orders.hour.value_counts()
        cell = avg.stack().idxmax()
        a, b = st.columns(2)
        with a:
            fig = px.bar(x=per_day.index, y=per_day.values, labels={"x": "", "y": "Transaksi/hari"},
                         color_discrete_sequence=[ui.TEAL])
            fig.update_traces(marker_cornerradius=6)
            ui.show(fig, 300, "Rata-rata transaksi per hari", legend=False)
        with b:
            hh = hours.sort_index()
            fig = px.bar(x=[f"{h:02d}" for h in hh.index], y=hh.values, labels={"x": "Jam", "y": "Transaksi"},
                         color_discrete_sequence=[ui.SKY])
            fig.update_traces(marker_cornerradius=6)
            ui.show(fig, 300, "Total transaksi per jam", legend=False)
        ui.insight([f"Hari tersibuk: <b>{per_day.idxmax()}</b> ({ui.num(per_day.max(), 1)} transaksi/hari); "
                    f"tersepi: <b>{per_day.idxmin()}</b> ({ui.num(per_day.min(), 1)}).",
                    f"Jam tersibuk: <b>{hours.idxmax():02d}.00–{hours.idxmax() + 1:02d}.00</b>; "
                    f"kombinasi paling ramai: <b>{cell[0]} jam {cell[1]:02d}.00</b>."])
    with t3:
        a, b = st.columns([1, 1.25])
        cat = df.groupby("category_name", as_index=False).line_total.sum().sort_values("line_total", ascending=False)
        cat["share"] = cat.line_total / cat.line_total.sum()
        with a:
            cs = cat.sort_values("share")
            fig = px.bar(cs, x="share", y="category_name", orientation="h", text=cs.share.map(lambda v: ui.pct(v)),
                         labels={"share": "Kontribusi penjualan", "category_name": ""}, color_discrete_sequence=[ui.TEAL])
            fig.update_traces(marker_cornerradius=6, textposition="outside", cliponaxis=False,
                              hovertemplate="%{y}: %{x:.1%}<extra></extra>")
            fig.update_xaxes(tickformat=".0%", range=[0, cs.share.max() * 1.25])
            ui.show(fig, 60 + 30 * len(cs) if len(cs) > 6 else 400, "Product Category Share", legend=False)
        with b:
            top = (df.groupby("product_name", as_index=False).agg(qty=("quantity", "sum"), rev=("line_total", "sum"))
                     .nlargest(10, "qty").sort_values("qty"))
            fig = px.bar(top, x="qty", y="product_name", orientation="h", text=top.qty.map(ui.num),
                         color_discrete_sequence=[ui.BERRY], labels={"qty": "Unit terjual", "product_name": ""})
            fig.update_traces(marker_cornerradius=6, textposition="outside", cliponaxis=False)
            fig.update_xaxes(range=[0, top.qty.max() * 1.18])
            ui.show(fig, 60 + 30 * len(cs) if len(cs) > 6 else 400, "10 produk terlaris (unit)", legend=False)
        first = (f"<b>{cat.iloc[0].category_name}</b> menyumbang {ui.pct(cat.iloc[0].share)} penjualan"
                 + (f", disusul {cat.iloc[1].category_name} ({ui.pct(cat.iloc[1].share)})." if len(cat) > 1
                    else " (hanya satu kategori yang dipilih)."))
        ui.insight([first, f"Produk terlaris: <b>{top.iloc[-1].product_name}</b> ({ui.num(top.iloc[-1].qty)} unit)."])
        with st.expander("Tabel kontribusi kategori"):
            st.dataframe(cat.assign(**{"Penjualan": cat.line_total.map(ui.money), "Kontribusi": cat.share.map(ui.pct)})
                         [["category_name", "Penjualan", "Kontribusi"]].rename(columns={"category_name": "Kategori"}),
                         hide_index=True, width="stretch")
    with t4:
        a, b = st.columns(2)
        ch = df.groupby("sales_channel", as_index=False).line_total.sum()
        with a:
            fig = px.pie(ch, names="sales_channel", values="line_total", hole=.62, color="sales_channel",
                         color_discrete_map=ui.CHANNEL_COLORS)
            fig.update_traces(textinfo="percent")
            ui.show(fig, 340, "Kontribusi kanal")
        with b:
            pay = df.drop_duplicates("order_key").groupby(["payment_method"]).size().reset_index(name="trx")
            pay = pay.sort_values("trx")
            fig = px.bar(pay, x="trx", y="payment_method", orientation="h", color_discrete_sequence=[ui.VIOLET],
                         labels={"trx": "Transaksi", "payment_method": ""})
            fig.update_traces(marker_cornerradius=6)
            ui.show(fig, 340, "Metode pembayaran (jumlah transaksi)", legend=False)
        typ = df.drop_duplicates("order_key").order_type.value_counts(normalize=True)
        online = (orders.channel != "Offline (Outlet)").mean()
        ui.insight([f"Pesanan online (ojol) = <b>{ui.pct(online)}</b> dari transaksi.",
                    "Tipe order: " + ", ".join(f"{k} {ui.pct(v)}" for k, v in typ.items()) + "."])
    with st.expander("Lihat data transaksi (300 baris pertama)"):
        st.dataframe(df.head(300), hide_index=True, width="stretch")
