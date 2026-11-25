import pandas as pd
import streamlit as st

import data
import ui
from analytics.apriori import LEVELS, TOPPING_CATEGORIES
from views.basket import controls, strength


def _topping_items(df, col):
    """Item (pada level terpilih) yang termasuk kategori topping."""
    if col == "category_name":
        return {c for c in df.category_name.unique() if c in TOPPING_CATEGORIES}
    return set(df.loc[df.category_name.isin(TOPPING_CATEGORIES), col].astype(str).unique())


def _label(item, toppings):
    """Beri awalan 'Topping' agar 'Boba' tidak tertukar dengan 'Boba Milk Tea'."""
    if item in toppings and not item.lower().startswith("topping"):
        return f"Topping {item}"
    return item


def _card(title, tag, meta, extra=""):
    lab, colr, bg = tag
    return (f'<div class="rule-card"><div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span class="rule-meta">{title}</span>'
            f'<span class="tag" style="color:{colr};background:{bg}">{lab}</span></div>'
            f'<div class="rule-items">{meta[0]}</div><div class="rule-meta">{meta[1]}</div>{extra}</div>')


def render():
    df = data.require_data()
    ui.page_header("Market Basket", "Rekomendasi Bundling",
                   "Paket promo dari pasangan menu yang paling kuat hubungannya, plus saran tambah topping.")
    res, p = controls(df, "bd")
    if not res["rules"]:
        st.warning("Tidak ada aturan dengan parameter ini. Ubah pengaturan di atas.")
        return
    disc = st.slider("Diskon paket yang disimulasikan (%)", 0, 30, 10, 5,
                     help="Hanya simulasi harga; keputusan akhir mempertimbangkan margin dan stok.")
    col = LEVELS[p["level"]]
    price = df.groupby(col).unit_price.median() if p["level"] != "Kategori" else None
    toppings = _topping_items(df, col)
    lbl = lambda x: ui.html.escape(_label(x, toppings))  # noqa: E731

    # Pisahkan: paket (tanpa topping) vs saran tambah topping (menu utama -> topping)
    seen, bundles, upsells, seen_up = set(), [], [], set()
    for r in res["rules"]:
        items = tuple(sorted(set(r["antecedent"] + r["consequent"])))
        has_top = any(i in toppings for i in items)
        if not has_top:
            if items not in seen:
                seen.add(items)
                bundles.append((items, r))
        else:
            # arah yang berguna untuk kasir: pembeli menu utama -> tawarkan topping
            if all(i not in toppings for i in r["antecedent"]) and all(i in toppings for i in r["consequent"]):
                if items not in seen_up:
                    seen_up.add(items)
                    upsells.append(r)

    # ---------- Paket bundling ----------
    rows = []
    if bundles:
        ui.section(f"{min(len(bundles), 9)} kandidat paket teratas",
                   "Diurutkan dari lift tertinggi. Pasangan yang berisi topping dipisahkan ke bagian saran tambah topping.")
        top = bundles[:9]
        for i in range(0, len(top), 3):
            cols = st.columns(3)
            for c, (k, (items, r)) in zip(cols, enumerate(top[i:i + 3], start=i + 1)):
                price_html = ""
                if price is not None:
                    normal = sum(price.get(x, 0) for x in items)
                    bundle = round(normal * (1 - disc / 100), -3)
                    price_html = (f'<div style="margin-top:10px;display:flex;gap:10px;align-items:baseline">'
                                  f'<span style="font-size:1.35rem;font-weight:800;color:#0B2D4F">{ui.money(bundle)}</span>'
                                  f'<span style="text-decoration:line-through;color:#8A97AA">{ui.money(normal)}</span></div>')
                    rows.append({"Jenis": "Paket", "Isi": " + ".join(items), "Harga normal": normal, "Harga paket": bundle,
                                 "Lift": round(r["lift"], 2), "Confidence (%)": round(r["confidence"] * 100, 1),
                                 "Transaksi bersama": r["count"]})
                meta = (" + ".join(lbl(x) for x in items),
                        f'Dibeli bersama di <b>{ui.num(r["count"])}</b> transaksi · confidence '
                        f'{ui.pct(r["confidence"], 0)} · lift {ui.num(r["lift"], 2)}×')
                c.markdown(_card(f"PAKET #{k}", strength(r["lift"]), meta, price_html), unsafe_allow_html=True)
    else:
        st.info("Belum ada pasangan menu utama yang cukup kuat untuk dijadikan paket. Coba turunkan batas di pengaturan.")

    # ---------- Saran tambah topping (upselling) ----------
    if upsells:
        ui.section("Saran tambah topping (upselling)",
                   "Bukan paket diskon: tawarkan topping ini saat pelanggan memesan menu di sebelah kiri.")
        top = upsells[:6]
        for i in range(0, len(top), 3):
            cols = st.columns(3)
            for c, r in zip(cols, top[i:i + 3]):
                base = " + ".join(lbl(x) for x in r["antecedent"])
                add = " + ".join(lbl(x) for x in r["consequent"])
                extra = ""
                if price is not None:
                    add_price = sum(price.get(x, 0) for x in r["consequent"])
                    extra = (f'<div style="margin-top:10px;font-size:.9rem;color:#0B2D4F">'
                             f'Tambahan <b>{ui.money(add_price)}</b> per pesanan</div>')
                    rows.append({"Jenis": "Tambah topping", "Isi": f'{" + ".join(r["antecedent"])} → {" + ".join(r["consequent"])}',
                                 "Harga normal": add_price, "Harga paket": None, "Lift": round(r["lift"], 2),
                                 "Confidence (%)": round(r["confidence"] * 100, 1), "Transaksi bersama": r["count"]})
                meta = (f"{base} → tawarkan {add}",
                        f'<b>{ui.pct(r["confidence"], 0)}</b> pembeli {base} juga menambah {add} · '
                        f'{ui.num(r["count"])} transaksi · lift {ui.num(r["lift"], 2)}×')
                c.markdown(_card("TAWARKAN SAAT PESAN", strength(r["lift"]), meta, extra), unsafe_allow_html=True)

    ui.insight([
        "Prioritaskan paket yang hubungannya kuat <b>dan</b> sering dibeli bersama: dampaknya ke penjualan paling terasa.",
        "Saran topping cukup diucapkan kasir (\"mau tambah boba?\"); tidak perlu diskon karena pelanggan sudah cenderung membelinya.",
        "Uji paket di satu kanal dulu (mis. GoFood) lalu bandingkan penjualan sebelum–sesudah promo.",
        "Harga paket hanya simulasi dari median harga jual; sesuaikan dengan HPP dan margin.",
    ], "Cara memakai rekomendasi")
    if rows:
        st.download_button("Unduh daftar rekomendasi (CSV)", pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
                           file_name="coolercity_rekomendasi_bundling.csv", mime="text/csv", icon=":material/download:")
