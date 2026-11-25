import pandas as pd
import streamlit as st

import data
import db
import kpi
import ui

UNIT_LABEL = {"rupiah": "Rupiah", "unit": "Unit", "per_day": "Transaksi/hari", "ratio": "Persen (%)", "lift": "Lift (×)"}


def render():
    ui.page_header("Kelola Data", "Target KPI",
                   "Atur target tiap KPI. Status di halaman Ringkasan KPI otomatis menyesuaikan.")
    try:
        df = data.warehouse()
        years = sorted(int(y) for y in df.year.unique()) if not df.empty else []
        tgt = data.targets()
    except Exception as exc:  # noqa: BLE001
        st.error("Database belum tersambung.")
        st.code(str(exc))
        return
    data_last = years[-1] if years else pd.Timestamp.today().year
    years = sorted(set(years) | {y for y in tgt.year.astype(int).unique() if y > 0} | {data_last + 1})
    year = st.segmented_control("Tahun target", years, default=data_last, key="tg_year",
                                help="Tahun setelah data terakhir disediakan untuk menyiapkan target tahun depan.") or data_last
    current, focus = kpi.target_lookup(tgt, year)
    specific = {r.kpi_code: float(r.target_value) for r in tgt[tgt.year.astype(int) == year].itertuples()}
    cats = sorted(df.category_name.unique()) if not df.empty else [focus]

    ui.howto("Target <b>tahunan</b> (penjualan & unit) berlaku untuk tahun yang dipilih. Target lain berlaku untuk "
             "<b>semua tahun</b>. Persentase ditulis sebagai angka persen, mis. 35 untuk 35%.")
    with st.form("targets"):
        values = {}
        for k in kpi.MAIN_KPIS:
            c1, c2 = st.columns([2, 1])
            arah = "minimal" if k.higher_is_better else "maksimal"
            scope = f"khusus {year}" if k.yearly else "semua tahun"
            code = k.code
            cur = current.get(code)
            if k.unit == "ratio" and cur is not None:
                cur = cur * 100
            c1.markdown(f"**{k.icon} {k.name}**  \n<span style='color:#5F7189;font-size:.85rem'>{k.definition} "
                        f"· target {arah} · {scope}</span>", unsafe_allow_html=True)
            if code == "category_share":
                focus_new = c1.selectbox("Kategori fokus", cats, index=cats.index(focus) if focus in cats else 0, key="tg_cat")
            step = {"rupiah": 1_000_000.0 if k.yearly else 1_000.0, "unit": 100.0, "per_day": 1.0, "ratio": 0.5, "lift": 0.1}[k.unit]
            values[code] = c2.number_input(UNIT_LABEL[k.unit], value=float(cur) if cur is not None else None, step=step,
                                           min_value=0.0, key=f"tg_{code}", placeholder="Belum diatur",
                                           format="%.0f" if k.unit in ("rupiah", "unit") else "%.2f")
            if cur is not None and k.unit in ("rupiah", "unit"):
                c2.caption("Saat ini: " + (ui.money(cur) if k.unit == "rupiah" else ui.num(cur) + " unit"))
            st.divider()
        saved = st.form_submit_button("Simpan target", type="primary", icon=":material/save:")
    if saved:
        user = st.session_state["user"]["username"]
        with data.connection() as conn:
            for k in kpi.MAIN_KPIS:
                v = values[k.code]
                v = None if v is None else (v / 100 if k.unit == "ratio" else v)
                y = year if k.yearly else 0
                if k.code == "category_share":
                    for old in [c for c in tgt.kpi_code if c.startswith("category_share|")]:
                        db.save_target(conn, 0, old, None, user)
                    db.save_target(conn, 0, f"category_share|{focus_new}", v, user)
                else:
                    db.save_target(conn, y, k.code, v, user)
        data.targets.clear()
        st.success("Target tersimpan.")
        st.rerun()
    with st.expander("Riwayat perubahan target"):
        show = tgt.copy()
        show["year"] = show.year.astype(int).map(lambda y: "Semua tahun" if y == 0 else str(y))
        st.dataframe(show.rename(columns={"year": "Tahun", "kpi_code": "KPI", "target_value": "Target",
                                          "updated_by": "Diubah oleh", "updated_at": "Waktu"}),
                     hide_index=True, width="stretch")
