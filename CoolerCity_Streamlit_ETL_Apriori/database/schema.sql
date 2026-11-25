-- CoolerCity Data Warehouse (Kimball Star Schema) - SQL Server
-- Semua tabel berada di schema [cc]. Script aman dijalankan berulang (hanya membuat yang belum ada).
-- Pemisah antar-statement: baris berisi GO.

IF SCHEMA_ID('cc') IS NULL EXEC('CREATE SCHEMA cc')
GO

-- ===================== STAGING (data mentah hasil Extract, termasuk baris yang ditolak) =====================
IF OBJECT_ID('cc.stg_sales','U') IS NULL
CREATE TABLE cc.stg_sales (
    stg_id              INT IDENTITY(1,1) PRIMARY KEY,
    source              NVARCHAR(20)  NOT NULL,
    file_name           NVARCHAR(255) NOT NULL,
    source_row          INT           NOT NULL,
    source_order_id     NVARCHAR(60)  NULL,
    order_datetime_raw  NVARCHAR(60)  NULL,
    order_datetime      DATETIME2(0)  NULL,
    order_type          NVARCHAR(30)  NULL,
    customer_name_raw   NVARCHAR(150) NULL,
    sku_raw             NVARCHAR(30)  NULL,
    item_name_raw       NVARCHAR(150) NULL,
    variant_raw         NVARCHAR(30)  NULL,
    quantity            DECIMAL(18,2) NULL,
    unit_price          DECIMAL(18,2) NULL,
    line_total          DECIMAL(18,2) NULL,
    payment_method      NVARCHAR(30)  NULL,
    status_raw          NVARCHAR(30)  NULL,
    sku                 NVARCHAR(30)  NULL,
    reject_reason       NVARCHAR(100) NULL   -- kosong = lolos validasi
)
GO

-- ===================== DIMENSI =====================
IF OBJECT_ID('cc.dim_date','U') IS NULL
CREATE TABLE cc.dim_date (
    date_key      INT PRIMARY KEY,          -- YYYYMMDD
    full_date     DATE NOT NULL,
    day_of_month  TINYINT NOT NULL,
    day_name      NVARCHAR(10) NOT NULL,
    day_of_week   TINYINT NOT NULL,         -- 1 = Senin
    is_weekend    BIT NOT NULL,
    month         TINYINT NOT NULL,
    month_name    NVARCHAR(12) NOT NULL,
    quarter       NVARCHAR(2) NOT NULL,
    year          SMALLINT NOT NULL
)
GO
IF OBJECT_ID('cc.dim_time','U') IS NULL
CREATE TABLE cc.dim_time (
    time_key    INT PRIMARY KEY,            -- HHMM
    hour        TINYINT NOT NULL,
    minute      TINYINT NOT NULL,
    time_label  NVARCHAR(5) NOT NULL,
    day_period  NVARCHAR(10) NOT NULL
)
GO
IF OBJECT_ID('cc.dim_product','U') IS NULL
CREATE TABLE cc.dim_product (
    sk_product     INT PRIMARY KEY,         -- surrogate key
    sku            NVARCHAR(30) NOT NULL UNIQUE,
    product_name   NVARCHAR(150) NOT NULL,
    base_product   NVARCHAR(150) NOT NULL,
    variant        NVARCHAR(30) NOT NULL,
    category_name  NVARCHAR(60) NOT NULL,
    list_price     DECIMAL(18,2) NULL,
    is_menu_item   BIT NOT NULL
)
GO
IF OBJECT_ID('cc.dim_channel','U') IS NULL
CREATE TABLE cc.dim_channel (
    sk_channel     INT PRIMARY KEY,
    sales_channel  NVARCHAR(30) NOT NULL UNIQUE,
    channel_type   NVARCHAR(30) NOT NULL
)
GO
IF OBJECT_ID('cc.dim_payment','U') IS NULL
CREATE TABLE cc.dim_payment (
    sk_payment      INT PRIMARY KEY,
    payment_method  NVARCHAR(30) NOT NULL UNIQUE
)
GO
IF OBJECT_ID('cc.dim_order_type','U') IS NULL
CREATE TABLE cc.dim_order_type (
    sk_order_type  INT PRIMARY KEY,
    order_type     NVARCHAR(30) NOT NULL UNIQUE
)
GO
IF OBJECT_ID('cc.dim_customer','U') IS NULL
CREATE TABLE cc.dim_customer (
    sk_customer       INT PRIMARY KEY,
    customer_name     NVARCHAR(150) NOT NULL UNIQUE,
    customer_segment  NVARCHAR(30) NOT NULL
)
GO

-- ===================== FAKTA (grain: 1 baris = 1 item dalam 1 transaksi) =====================
IF OBJECT_ID('cc.fact_sales','U') IS NULL
CREATE TABLE cc.fact_sales (
    sale_line_id     INT IDENTITY(1,1) PRIMARY KEY,
    order_key        NVARCHAR(80) NOT NULL,   -- kode sumber + nomor order asli (mis. POS-S240101-001)
    line_no          INT NOT NULL,
    source           NVARCHAR(20) NOT NULL,
    source_order_id  NVARCHAR(60) NOT NULL,
    date_key         INT NOT NULL REFERENCES cc.dim_date(date_key),
    time_key         INT NOT NULL REFERENCES cc.dim_time(time_key),
    sk_product       INT NOT NULL REFERENCES cc.dim_product(sk_product),
    sk_channel       INT NOT NULL REFERENCES cc.dim_channel(sk_channel),
    sk_payment       INT NOT NULL REFERENCES cc.dim_payment(sk_payment),
    sk_order_type    INT NOT NULL REFERENCES cc.dim_order_type(sk_order_type),
    sk_customer      INT NOT NULL REFERENCES cc.dim_customer(sk_customer),
    quantity         INT NOT NULL,
    unit_price       DECIMAL(18,2) NOT NULL,
    line_total       DECIMAL(18,2) NOT NULL,
    CONSTRAINT UQ_fact_order_line UNIQUE (order_key, line_no)
)
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_fact_order_key')
CREATE INDEX IX_fact_order_key ON cc.fact_sales(order_key)
GO

-- ===================== LOG ETL (tidak ikut dihapus saat full refresh) =====================
IF OBJECT_ID('cc.etl_log','U') IS NULL
CREATE TABLE cc.etl_log (
    run_id         INT IDENTITY(1,1) PRIMARY KEY,
    run_at         DATETIME2(0) NOT NULL,
    source_files   NVARCHAR(1000) NULL,
    raw_rows       INT NOT NULL,
    valid_rows     INT NOT NULL,
    rejected_rows  INT NOT NULL,
    orders         INT NOT NULL,
    revenue        DECIMAL(18,2) NOT NULL,
    notes          NVARCHAR(1000) NULL
)
GO

-- ===================== PENGGUNA APLIKASI & TARGET KPI (tidak tersentuh oleh ETL) =====================
IF OBJECT_ID('cc.app_user','U') IS NULL
CREATE TABLE cc.app_user (
    user_id          INT IDENTITY(1,1) PRIMARY KEY,
    username         NVARCHAR(50)  NOT NULL UNIQUE,
    full_name        NVARCHAR(100) NOT NULL,
    email            NVARCHAR(150) NULL,
    password_hash    NVARCHAR(300) NOT NULL,
    role             NVARCHAR(20)  NOT NULL,   -- Admin | Manajemen
    status           NVARCHAR(20)  NOT NULL,   -- pending | active | rejected | inactive
    failed_attempts  INT NOT NULL DEFAULT 0,
    locked_until     DATETIME2(0) NULL,
    created_at       DATETIME2(0) NOT NULL,
    approved_by      NVARCHAR(50) NULL,
    last_login       DATETIME2(0) NULL
)
GO
IF OBJECT_ID('cc.kpi_target','U') IS NULL
CREATE TABLE cc.kpi_target (
    year          SMALLINT NOT NULL,          -- 0 = berlaku untuk semua tahun yang tidak punya target khusus
    kpi_code      NVARCHAR(40) NOT NULL,
    target_value  DECIMAL(18,4) NOT NULL,
    updated_by    NVARCHAR(50) NULL,
    updated_at    DATETIME2(0) NOT NULL,
    CONSTRAINT PK_kpi_target PRIMARY KEY (year, kpi_code)
)
GO

-- ===================== VIEW untuk dashboard / Power BI =====================
CREATE OR ALTER VIEW cc.vw_sales AS
SELECT f.order_key, f.line_no, f.source, f.source_order_id,
       d.full_date, d.year, d.quarter, d.month, d.month_name, d.day_name, d.day_of_week, d.is_weekend,
       t.hour, t.time_label, t.day_period,
       p.sku, p.product_name, p.base_product, p.variant, p.category_name, p.is_menu_item,
       c.sales_channel, c.channel_type, pm.payment_method, ot.order_type,
       cu.customer_name, cu.customer_segment,
       f.quantity, f.unit_price, f.line_total
FROM cc.fact_sales f
LEFT JOIN cc.dim_date d        ON f.date_key = d.date_key
LEFT JOIN cc.dim_time t        ON f.time_key = t.time_key
LEFT JOIN cc.dim_product p     ON f.sk_product = p.sk_product
LEFT JOIN cc.dim_channel c     ON f.sk_channel = c.sk_channel
LEFT JOIN cc.dim_payment pm    ON f.sk_payment = pm.sk_payment
LEFT JOIN cc.dim_order_type ot ON f.sk_order_type = ot.sk_order_type
LEFT JOIN cc.dim_customer cu   ON f.sk_customer = cu.sk_customer
GO
