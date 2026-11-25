# CoolerCity — Streamlit ETL, Data Warehouse & Apriori

Aplikasi BI dengan menu:

| Grup | Halaman | Admin | Manajemen |
|---|---|---|---|
| Dashboard | Ringkasan KPI (status target), Analisis Penjualan | ✔ | ✔ |
| Market Basket | Analisis Apriori, Rekomendasi Bundling | ✔ | ✔ |
| Kelola Data | ETL & Data Warehouse, Target KPI, Pengguna | ✔ | – |
| Akun | Akun Saya (ganti password) | ✔ | ✔ |
Data yang dipakai adalah **data simulasi** CoolerCity yang dibuat mengikuti format export POS dan aplikasi ojol.

## Arsitektur

```
Export POS Outlet ─┐
Export Ojol        ├─► Extract (dibaca sebagai teks) ─► Transform (pandas) ─► Load (SQL Server, schema cc) ─► Dashboard & Apriori
(GoFood/Grab/Shopee)│        staging                    validasi, SKU,          stg_sales, 7 dimensi,
Daftar Menu ───────┘                                   surrogate key            fact_sales, etl_log
```

## File sumber yang diterima

| File | Sheet | Keterangan |
|---|---|---|
| Daftar Menu | `Daftar Menu` | **Wajib.** SKU, Kategori, Nama Menu, Varian, Harga |
| Export POS Outlet | `Laporan Penjualan per Item` | Transaksi offline (dine in / take away) |
| Export Ojol | `GoFood`, `GrabFood`, `ShopeeFood` | Satu sheet per platform, kolom & format berbeda |

File dikenali dari **nama sheet**, jadi semua file bisa di-upload sekaligus.

## Aturan Transform

- **Ditolak (dicatat di `cc.stg_sales.reject_reason`):** status batal (Dibatalkan / Cancelled / CANCELLED), status tidak dikenali,
  tanggal atau angka tidak valid, produk tidak ada di Daftar Menu, baris duplikat persis, baris TOTAL.
- **Format tanggal eksplisit per sumber** (`dd/mm/yyyy HH:MM` POS, ISO GoFood, `01 Jan 2024 12:44 PM` Grab, tanggal + jam terpisah Shopee),
  sehingga 05/01 tidak tertukar menjadi 1 Mei.
- **Angka**: `20000`, `20.000`, `Rp20.000`, dan `20,000.00` (Grab) dikenali.
- **Mapping produk**: POS memakai SKU; ojol dicocokkan dari nama menu (`(M)/(L)`, huruf kapital, `Nama - Varian`).
- **Surrogate key** dibuat saat Transform: `sk_product`, `sk_channel`, `sk_payment`, `sk_order_type`, `sk_customer`;
  `date_key` = YYYYMMDD, `time_key` = HHMM. `order_key` = kode sumber + nomor order asli (mis. `POS-S240101-001`, `SPF-1154…`).
- **Pelanggan**: nama POS dirapikan (nama depan saja → nama lengkap bila hanya ada satu kandidat). Nama pelanggan ojol disamarkan
  oleh platform sehingga tidak dapat dihubungkan lintas kanal.
- Harga yang berbeda dari Daftar Menu atau Total ≠ Qty × Harga dilaporkan sebagai peringatan (tidak ditolak).

## Star Schema (schema `cc`)

`fact_sales` (grain: 1 item dalam 1 transaksi) → `dim_date`, `dim_time`, `dim_product`, `dim_channel`, `dim_payment`,
`dim_order_type`, `dim_customer`. Tambahan: `stg_sales` (staging, termasuk baris ditolak), `etl_log` (riwayat ETL, tidak dihapus),
dan view `vw_sales` (gabungan fakta + dimensi, dipakai dashboard; bisa juga untuk Power BI).

## Apriori

- 1 keranjang = 1 `order_key`. Level item: **Produk (ukuran digabung)**, **Produk + varian ukuran**, atau **Kategori**.
- Default: support 5%, confidence 50%, lift ≥ 1, maksimal 3 item.
- Kemasan (Cup/Cone) bisa dikeluarkan; transaksi yang isinya hanya topping/kemasan bisa diabaikan.
- Filter tahun, kanal, dan tipe order **memilih transaksi**, tidak memotong isi keranjang.

## KPI & target

| KPI | Cara hitung | Target default (bisa diubah) |
|---|---|---|
| Total Sales Revenue | Σ line_total | 2024: Rp420 jt · 2025: Rp540 jt (per tahun) |
| Total Quantity Sold | Σ quantity | 2024: 27.000 · 2025: 32.000 unit (per tahun) |
| Average Basket Size | omzet ÷ jumlah transaksi | ≥ Rp75.000 |
| Peak Hours & Days Volume | rata-rata transaksi/hari pada hari tersibuk (+ jam tersibuk) | ≥ 24 transaksi/hari |
| Product Category Share | kontribusi kategori fokus terhadap omzet | Milk Tea Series ≥ 35% |
| Lift Ratio | rata-rata lift aturan Apriori (produk, support 5%, confidence 50%) | ≥ 1,5 |
| Pertumbuhan Penjualan (YoY) *tambahan* | omzet tahun ini ÷ tahun lalu − 1 | ≥ 15% |
| Transaksi Multi-Produk *tambahan* | % transaksi berisi ≥2 produk | ≥ 90% |
| Tingkat Pembatalan *tambahan* | order batal ÷ (valid + batal), dari staging | ≤ 1,5% |

Status: **Tercapai** ≥100% target · **Hampir** 90–99% · **Belum** <90% (untuk pembatalan: semakin kecil semakin baik).
Target disimpan di tabel `cc.kpi_target` (year = 0 berarti berlaku untuk semua tahun) dan diubah lewat menu **Target KPI**.
Target default hanya contoh; sesuaikan dengan target perusahaan/penelitian.

## Login & pengguna

- **Admin bawaan** dibuat dengan `python setup_login.py` (disimpan sebagai hash di `.env`). Akun ini selalu bisa masuk walau database bermasalah.
- **Daftar akun** di halaman login → status *menunggu* → Admin menyetujui di menu **Pengguna** dan memilih peran (Admin / Manajemen).
  Pendaftaran terbuka tanpa persetujuan sengaja tidak dipakai karena dashboard berisi data penjualan internal.
- Password di-hash PBKDF2-SHA256 (260.000 iterasi), minimal 8 karakter berisi huruf & angka.
- Salah password 5 kali → akun dikunci 15 menit. Admin dapat reset password, mengubah peran, atau menonaktifkan akun.
- Data pengguna di tabel `cc.app_user`; tidak ikut terhapus saat ETL.

## Menjalankan di Windows

1. Instal Python 3.10+ dan **Microsoft ODBC Driver 18 for SQL Server**; pastikan SQL Server dapat diakses dari SSMS.
2. Buat database kosong, mis. `CREATE DATABASE dw_coolercity;` (tabel dibuat otomatis oleh aplikasi).
3. Salin `.env.example` menjadi `.env`, isi `SQL_SERVER`, `SQL_DATABASE`, dan `SQL_DRIVER` (cek driver dengan `python -c "import pyodbc; print(pyodbc.drivers())"`).
4. Jalankan:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup_login.py
streamlit run app.py
```

5. Buka `http://localhost:8501`, login, pilih **ETL & Data Warehouse**, upload ketiga file, periksa rekonsiliasi,
   centang konfirmasi, lalu tekan **Jalankan Load ke SQL Server**.

Jika aktivasi PowerShell diblokir: `.venv\Scripts\python.exe -m pip install -r requirements.txt` lalu
`.venv\Scripts\python.exe -m streamlit run app.py`.

## Catatan

- Load adalah **full refresh dalam satu transaksi**: jika gagal, isi lama tidak berubah. `etl_log` tidak ikut dihapus.
- Tabel lama versi sebelumnya (`dbo.cc_*`) tidak dipakai lagi dan tidak diubah; boleh dihapus manual bila tidak diperlukan.
- Pengecekan hasil ETL bisa dibandingkan dengan file `KUNCI_Validasi_ETL_CoolerCity.xlsx`
  (12.500 transaksi, 47.900 baris item, omzet Rp968.662.000 untuk data simulasi v5).
- Login lokal memakai hash PBKDF2 di `.env`; cocok untuk demo satu akun. Jangan unggah `.env` ke GitHub.
- Streamlit Community Cloud tidak bisa mengakses SQL Server yang hanya ada di localhost laptop.

## Struktur proyek

- `app.py` — titik masuk: login/daftar, navigasi sesuai peran.
- `views/` — halaman: `overview` (KPI), `sales`, `basket` (Apriori), `bundling`, `etl_view`, `targets_view`, `users_view`, `account`.
- `ui.py` — tema, kartu KPI, gaya grafik; `.streamlit/config.toml` — warna tema; `assets/` — logo.
- `kpi.py` — definisi KPI, target default, perhitungan capaian.
- `data.py` — akses data dengan cache.
- `auth.py` — hash password, login + penguncian, pendaftaran.
- `etl/pipeline.py` — adapter sumber, validasi, mapping SKU, surrogate key, load.
- `db.py` — koneksi SQL Server, inisialisasi skema, query data warehouse, target, dan pengguna.
- `database/schema.sql` — DDL star schema + staging + log + pengguna + target + view (pemisah batch `GO`).
- `analytics/apriori.py` — pembentukan keranjang dan algoritma Apriori.
- `tests/test_etl.py` — uji ETL & Apriori tanpa SQL Server (`python -m tests.test_etl <folder_data>`).
