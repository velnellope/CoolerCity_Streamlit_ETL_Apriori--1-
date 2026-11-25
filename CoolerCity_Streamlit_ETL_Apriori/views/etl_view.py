import os

import pandas as pd
import streamlit as st

import data
import db
import ui
from etl.pipeline import load_warehouse, run_etl


def render():
    ui.page_header("Kelola Data", "ETL & Data Warehouse",
                   "Upload export mentah, periksa hasil validasi, lalu muat ke star schema SQL Server.")
    steps = st.columns(3)
    for c, (n, t, d) in zip(steps, [("1", "Extract", "Upload Daftar Menu + export POS / Ojol"),
                                    ("2", "Transform", "Validasi, buang batal & duplikat, cocokkan SKU"),
                                    ("3", "Load", "Tulis ke schema cc (7 dimensi + fakta)")]):
        c.markdown(f'<div class="kpi" style="gap:4px"><div class="kpi-name"><div class="kpi-icon" style="background:#E2F3FA">'
                   f'{n}</div>{t}</div><div class="kpi-note">{d}</div></div>', unsafe_allow_html=True)
    st.write("")
    with st.container(border=True):
        st.markdown("**📤 Upload file sumber**")
        st.caption(f"Tujuan: `{os.getenv('SQL_SERVER', 'localhost')}` / `{os.getenv('SQL_DATABASE', 'dw_coolercity')}`. "
                   "File dikenali dari nama sheet, jadi boleh di-upload sekaligus.")
        uploads = st.file_uploader("Pilih file (.xlsx / .csv)", type=["xlsx", "csv"], accept_multiple_files=True)
    if not uploads:
        _history()
        return
    files = [(u.name, u.getvalue()) for u in uploads]
    sig = tuple((n, len(b)) for n, b in files)
    if st.session_state.get("etl_sig") != sig:
        try:
            with st.spinner("Extract & Transform..."):
                res, notes = run_etl(files)
            st.session_state.update(etl_sig=sig, etl_res=res, etl_notes=notes, etl_files=[n for n, _ in files], etl_err=None)
        except Exception as exc:  # noqa: BLE001
            st.session_state.update(etl_sig=sig, etl_res=None, etl_err=str(exc))
    if st.session_state.get("etl_err"):
        st.error("Validasi gagal: " + st.session_state["etl_err"])
        return
    res = st.session_state["etl_res"]
    s = res.stats
    st.success(f"Validasi selesai untuk periode {s['period']}. Data **belum** ditulis ke database.")
    a, b, c, d, e = st.columns(5)
    a.metric("Baris mentah", ui.num(s["raw_rows"]))
    b.metric("Baris valid", ui.num(s["valid_rows"]))
    c.metric("Baris ditolak", ui.num(s["rejected_rows"]))
    d.metric("Transaksi valid", ui.num(s["unique_orders"]))
    e.metric("Omzet valid", ui.money(s["revenue"], short=True))
    for w in res.warnings:
        st.warning(w)
    t1, t2, t3, t4 = st.tabs(["Rekonsiliasi", "Baris ditolak", "Pratinjau tabel", "File dikenali"])
    with t1:
        summ = res.summary.copy()
        summ["Omzet (Rp)"] = summ["Omzet (Rp)"].map(ui.money)
        for col in ["Baris mentah", "Baris valid", "Baris ditolak", "Transaksi valid"]:
            summ[col] = summ[col].astype(int)
        st.dataframe(summ, hide_index=True, width="stretch")
        ui.howto("Baris mentah = baris valid + baris ditolak. Bandingkan TOTAL dengan angka di file kunci validasi.")
    with t2:
        if res.rejected.empty:
            st.write("Tidak ada baris ditolak.")
        else:
            reasons = res.rejected.groupby(["source", "reject_reason"]).size().reset_index(name="Baris")
            st.dataframe(reasons.rename(columns={"source": "Sumber", "reject_reason": "Alasan"}), hide_index=True, width="stretch")
            st.download_button("Unduh detail baris ditolak (CSV)",
                               res.rejected[["source", "file_name", "source_row", "source_order_id", "order_datetime_raw",
                                             "item_name_raw", "quantity", "unit_price", "status_raw", "reject_reason"]]
                               .to_csv(index=False).encode("utf-8-sig"), file_name="coolercity_baris_ditolak.csv",
                               mime="text/csv", icon=":material/download:")
    with t3:
        names = ["fact_sales"] + list(res.dims)
        pick = st.segmented_control("Tabel", names, default="fact_sales", key="etl_tbl") or "fact_sales"
        tbl = res.fact if pick == "fact_sales" else res.dims[pick]
        st.caption(f"{ui.num(len(tbl))} baris")
        st.dataframe(tbl.head(50), hide_index=True, width="stretch")
    with t4:
        for n in st.session_state["etl_notes"]:
            st.write("• " + n)
    with st.container(border=True):
        st.markdown("**Muat ke SQL Server**")
        st.caption("Full refresh: isi staging, dimensi, dan fakta diganti. Pengguna, target KPI, dan log ETL tidak dihapus. "
                   "Jika gagal di tengah jalan, data lama dikembalikan (rollback).")
        agree = st.checkbox("Saya sudah memeriksa hasil validasi dan setuju data lama diganti")
        if st.button("Jalankan Load", type="primary", disabled=not agree, icon=":material/upload:"):
            conn = None
            try:
                with st.spinner("Memuat ke SQL Server..."):
                    conn = db.connect()
                    db.initialize(conn)
                    load_warehouse(conn, res, st.session_state["etl_files"])
                data.clear_all()
                st.success("Load berhasil. Dashboard sudah memakai data terbaru.")
                st.balloons()
            except Exception as exc:  # noqa: BLE001
                if conn is not None:
                    conn.rollback()
                st.error("Load gagal, data lama tidak berubah.")
                st.code(str(exc))
            finally:
                if conn is not None:
                    conn.close()
    _history()


def _history():
    with st.expander("Riwayat ETL"):
        try:
            with data.connection() as conn:
                log = db.read_etl_log(conn)
            st.dataframe(log, hide_index=True, width="stretch") if not log.empty else st.caption("Belum ada riwayat.")
        except Exception as exc:  # noqa: BLE001
            st.caption("Belum bisa membaca log: " + str(exc)[:200])
    with st.expander("Struktur star schema"):
        st.code("""                 dim_date     dim_time
                        \\     /
 dim_product ——— fact_sales ——— dim_channel
                  /    |    \\
     dim_customer  dim_payment  dim_order_type""", language="text")
        st.caption("Grain fakta: 1 baris = 1 item dalam 1 transaksi. Tabel pendukung: stg_sales, etl_log, app_user, "
                   "kpi_target, dan view vw_sales.")
