"""Uji ETL + Apriori tanpa SQL Server.

Pakai:  python -m tests.test_etl <folder berisi file export, Daftar Menu, KUNCI, dan v5 (opsional)>
Load diuji ke SQLite yang tabelnya diturunkan otomatis dari database/schema.sql (kolom & foreign key sama).
"""
import re
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.apriori import build_baskets, mine_rules  # noqa: E402
from db import schema_batches  # noqa: E402
from etl.pipeline import load_warehouse, run_etl  # noqa: E402


def sqlite_from_schema():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS cc")
    con.execute("PRAGMA cc.foreign_keys = ON")
    con.execute("PRAGMA foreign_keys = ON")
    con.create_function("SYSDATETIME", 0, lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    for b in schema_batches():
        m = re.search(r"CREATE TABLE (cc\.\w+) \((.*)\)\s*$", b, re.S)
        if not m:
            continue
        body = re.sub(r"--[^\n]*", "", m.group(2))
        body = re.sub(r"INT IDENTITY\(1,1\) PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", body)
        body = re.sub(r"NVARCHAR\(\d+\)|DATETIME2\(0\)|DATE\b", "TEXT", body)
        body = re.sub(r"\b(TINYINT|SMALLINT|BIT)\b", "INTEGER", body)
        body = re.sub(r"DECIMAL\(\d+,\d+\)", "REAL", body)
        body = re.sub(r"REFERENCES cc\.", "REFERENCES ", body)
        con.execute(f"CREATE TABLE {m.group(1)} ({body})")
    return con


def main(folder):
    d = Path(folder)
    names = ["Export_POS_Outlet_CoolerCity_2024-2025.xlsx", "Export_Ojol_CoolerCity_2024-2025.xlsx",
             "Daftar_Menu_CoolerCity.xlsx"]
    files = [(n, (d / n).read_bytes()) for n in names]
    t = time.time()
    res, notes = run_etl(files)
    print(f"ETL transform {time.time() - t:.1f}s")
    print(res.summary.to_string(index=False))
    print("ditolak:", res.stats["rejected_by_reason"])
    for w in res.warnings:
        print("PERINGATAN:", w)

    key_file = d / "KUNCI_Validasi_ETL_CoolerCity.xlsx"
    if key_file.exists():
        exp = pd.read_excel(key_file, "Hasil yang seharusnya").set_index("pemeriksaan").nilai_seharusnya
        assert res.stats["unique_orders"] == exp["Total transaksi valid"], "jumlah transaksi beda"
        assert res.stats["valid_rows"] == exp["Total baris item valid"], "jumlah baris beda"
        assert round(res.stats["revenue"]) == exp["Total omzet (Rp)"], "omzet beda"
        assert res.stats["rejected_by_reason"].get("Baris duplikat", 0) == exp["Baris duplikat di export POS"]
        print("OK  cocok dengan KUNCI (transaksi, baris, omzet, duplikat)")
        v5 = d / "Data_CoolerCity_Simulasi_Realistis_v5.xlsx"
        if v5.exists():
            mp = pd.read_excel(key_file, "Mapping ke v5", dtype=str)
            code = {"POS Outlet": "POS", "GoFood": "GOF", "GrabFood": "GRB", "ShopeeFood": "SPF"}
            mp["order_key"] = mp.sumber.map(code) + "-" + mp.id_di_export
            hv = pd.read_excel(v5, "order_header", dtype={"order_no": str})
            f = res.fact.groupby("order_key").agg(date_key=("date_key", "first"), lines=("line_no", "max"),
                                                 total=("line_total", "sum")).reset_index()
            chk = f.merge(mp, on="order_key").merge(hv, left_on="order_no_v5", right_on="order_no", suffixes=("", "_v5"))
            assert len(chk) == len(f) == len(hv), "mapping order tidak lengkap"
            assert (chk.date_key == chk.date_key_v5).all(), "ada tanggal tertukar (dd/mm vs mm/dd)"
            assert (chk.lines == chk.item_lines).all() and (chk.total == chk.order_total).all(), "isi order beda"
            print("OK  setiap order sama dengan v5 (tanggal, jumlah item, total)")

    # Apriori dari data hasil ETL (meniru view vw_sales)
    p = res.dims["dim_product"]
    vw = res.fact.merge(p, on="sk_product").merge(res.dims["dim_channel"], on="sk_channel")
    for level, expect in [("Produk (ukuran digabung)", 12), ("Kategori", None)]:
        r = mine_rules(build_baskets(vw, level), 0.05, 0.5, 1.0, 3)
        print(f"Apriori {level}: {r['orders']:,} keranjang, {r['total_rules']} aturan; teratas:",
              " + ".join(r["rules"][0]["antecedent"]), "→", " + ".join(r["rules"][0]["consequent"]),
              f"lift {r['rules'][0]['lift']:.2f}")
        if expect is not None:
            assert r["total_rules"] == expect

    con = sqlite_from_schema()
    t = time.time()
    load_warehouse(con, res, names)
    load_warehouse(con, res, names)  # dijalankan dua kali: full refresh tidak boleh dobel
    counts = {t_: con.execute(f"SELECT COUNT(*) FROM cc.{t_}").fetchone()[0]
              for t_ in ["stg_sales", "fact_sales", "dim_product", "dim_date", "etl_log"]}
    print(f"Load uji {time.time() - t:.1f}s:", counts)
    assert counts["fact_sales"] == res.stats["valid_rows"] and counts["stg_sales"] == res.stats["raw_rows"]
    assert counts["etl_log"] == 2
    assert con.execute("PRAGMA cc.foreign_key_check").fetchall() == []
    print("OK  load + foreign key valid, full refresh tidak menggandakan data")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
