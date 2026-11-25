"""Akses data dengan cache Streamlit. Semua halaman membaca data lewat modul ini."""
from contextlib import contextmanager

import pandas as pd
import streamlit as st

import db
from analytics.apriori import build_baskets, mine_rules
from kpi import DEFAULT_TARGETS


@contextmanager
def connection():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@st.cache_resource(show_spinner=False)
def ensure_schema():
    """Dijalankan sekali per server: buat tabel yang belum ada dan isi target contoh bila kosong."""
    with connection() as conn:
        db.initialize(conn)
        db.seed_targets(conn, DEFAULT_TARGETS)
    return True


def db_ready():
    try:
        return ensure_schema()
    except Exception as exc:  # noqa: BLE001 - ditampilkan ke pengguna
        st.session_state["db_error"] = str(exc)
        return False


@st.cache_data(ttl=300, show_spinner="Memuat data warehouse...")
def warehouse():
    with connection() as conn:
        df = db.read_warehouse(conn)
    if df.empty:
        return df
    df["full_date"] = pd.to_datetime(df["full_date"])
    for c in ["quantity", "unit_price", "line_total", "year", "month", "hour", "is_menu_item", "is_weekend"]:
        df[c] = pd.to_numeric(df[c])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def cancellations():
    with connection() as conn:
        return db.read_cancellations(conn)


@st.cache_data(ttl=60, show_spinner=False)
def targets():
    with connection() as conn:
        return db.read_targets(conn)


@st.cache_data(show_spinner=False)
def rules_for(years: tuple, channels: tuple, order_types: tuple, level: str, excl: bool, drop_top: bool,
              sup: float, conf: float, lift: float):
    data = warehouse()
    data = data[data.year.isin(years) & data.sales_channel.isin(channels) & data.order_type.isin(order_types)]
    return mine_rules(build_baskets(data, level, excl, drop_top), sup, conf, lift, max_size=3)


def clear_all():
    warehouse.clear()
    cancellations.clear()
    targets.clear()
    rules_for.clear()


def require_data():
    """Ambil data warehouse; hentikan halaman dengan pesan yang jelas bila belum tersedia."""
    try:
        df = warehouse()
    except Exception as exc:  # noqa: BLE001
        st.error("Belum bisa membaca SQL Server. Pastikan server aktif dan isi `.env` sudah benar.")
        with st.expander("Detail teknis"):
            st.code(str(exc))
        st.stop()
    if df.empty:
        st.info("Data warehouse masih kosong. Admin perlu menjalankan ETL di menu **Kelola Data → ETL & Data Warehouse**.")
        st.stop()
    return df
