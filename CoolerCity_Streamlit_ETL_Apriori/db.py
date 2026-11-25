"""Koneksi SQL Server, pembuatan skema, dan query baca/tulis untuk dashboard, pengguna, dan target KPI.

Query ditulis dengan SQL standar (tanpa TOP/MERGE) dan parameter `?` agar aman dari SQL injection."""
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
SCHEMA = "cc"


def connect():
    import pyodbc  # di-import di sini agar modul lain tetap bisa dipakai tanpa driver ODBC
    driver = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("SQL_SERVER", "localhost")
    database = os.getenv("SQL_DATABASE", "dw_coolercity")
    trusted = os.getenv("SQL_TRUSTED", "yes").lower() == "yes"
    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}", "Encrypt=yes",
             "TrustServerCertificate=yes"]
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend([f'UID={os.getenv("SQL_USER", "")}', f'PWD={os.getenv("SQL_PASSWORD", "")}'])
    return pyodbc.connect(";".join(parts) + ";", timeout=15, autocommit=False)


def schema_batches():
    sql = (Path(__file__).parent / "database/schema.sql").read_text(encoding="utf-8")
    return [b.strip() for b in re.split(r"^\s*GO\s*$", sql, flags=re.M | re.I) if b.strip()]


def initialize(conn):
    """Buat schema/tabel/view yang belum ada lalu commit."""
    cur = conn.cursor()
    for batch in schema_batches():
        cur.execute(batch)
    conn.commit()


def _df(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=cols)


def _exec(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    return cur.rowcount


# ------------------------------------------------------------------ data warehouse
def read_warehouse(conn):
    return _df(conn, f"SELECT * FROM {SCHEMA}.vw_sales")


def read_etl_log(conn, limit=20):
    return _df(conn, f"SELECT * FROM {SCHEMA}.etl_log ORDER BY run_id DESC").head(limit)


def read_cancellations(conn):
    """Order yang dibatalkan (dari staging): dipakai untuk KPI tingkat pembatalan."""
    df = _df(conn, f"SELECT source, source_order_id, order_datetime FROM {SCHEMA}.stg_sales "
                   f"WHERE reject_reason = ?", ("Transaksi dibatalkan",))
    if df.empty:
        return df
    df["order_datetime"] = pd.to_datetime(df.order_datetime)
    return df.drop_duplicates(["source", "source_order_id"])


# ------------------------------------------------------------------ target KPI
def read_targets(conn):
    return _df(conn, f"SELECT year, kpi_code, target_value, updated_by, updated_at FROM {SCHEMA}.kpi_target")


def save_target(conn, year, code, value, user):
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {SCHEMA}.kpi_target WHERE year = ? AND kpi_code = ?", (int(year), code))
    if value is not None:
        cur.execute(f"INSERT INTO {SCHEMA}.kpi_target (year, kpi_code, target_value, updated_by, updated_at) "
                    f"VALUES (?, ?, ?, ?, ?)", (int(year), code, float(value), user, datetime.now().replace(microsecond=0)))
    conn.commit()


def seed_targets(conn, defaults):
    """Isi target contoh hanya jika tabel target masih kosong."""
    if not read_targets(conn).empty:
        return False
    cur = conn.cursor()
    now = datetime.now().replace(microsecond=0)
    for (year, code), value in defaults.items():
        cur.execute(f"INSERT INTO {SCHEMA}.kpi_target (year, kpi_code, target_value, updated_by, updated_at) "
                    f"VALUES (?, ?, ?, ?, ?)", (year, code, float(value), "default", now))
    conn.commit()
    return True


# ------------------------------------------------------------------ pengguna
USER_COLS = "user_id, username, full_name, email, password_hash, role, status, failed_attempts, locked_until, created_at, approved_by, last_login"


def get_user(conn, username):
    df = _df(conn, f"SELECT {USER_COLS} FROM {SCHEMA}.app_user WHERE LOWER(username) = LOWER(?)", (username,))
    return None if df.empty else df.iloc[0].to_dict()


def list_users(conn):
    return _df(conn, f"SELECT {USER_COLS} FROM {SCHEMA}.app_user ORDER BY created_at DESC")


def create_user(conn, username, full_name, email, password_hash, role, status, approved_by=None):
    _exec(conn, f"INSERT INTO {SCHEMA}.app_user (username, full_name, email, password_hash, role, status, failed_attempts, "
                f"created_at, approved_by) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
          (username, full_name, email, password_hash, role, status, datetime.now().replace(microsecond=0), approved_by))


def update_user(conn, username, **fields):
    allowed = {"full_name", "email", "password_hash", "role", "status", "failed_attempts", "locked_until", "approved_by",
               "last_login"}
    keys = [k for k in fields if k in allowed]
    if not keys:
        return 0
    sets = ", ".join(f"{k} = ?" for k in keys)
    return _exec(conn, f"UPDATE {SCHEMA}.app_user SET {sets} WHERE LOWER(username) = LOWER(?)",
                 tuple(fields[k] for k in keys) + (username,))


def count_active_admins(conn):
    df = _df(conn, f"SELECT COUNT(*) AS n FROM {SCHEMA}.app_user WHERE role = ? AND status = ?", ("Admin", "active"))
    return int(df.n.iloc[0])
