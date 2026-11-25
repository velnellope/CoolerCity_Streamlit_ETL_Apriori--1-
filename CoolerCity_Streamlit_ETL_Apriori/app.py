"""CoolerCity BI — export POS + ojol → ETL → SQL Server star schema → KPI, analisis penjualan, Apriori, bundling."""
import base64
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
st.set_page_config(page_title="CoolerCity · Business Intelligence", page_icon=os.path.join(ASSETS, "icon.png"), layout="wide",
                   initial_sidebar_state="expanded")

import auth  # noqa: E402
import data  # noqa: E402
import ui  # noqa: E402
from views import account, basket, bundling, etl_view, overview, sales, targets_view, users_view  # noqa: E402

ui.inject_css()


def auth_screen():
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        with open(os.path.join(ASSETS, "logo.png"), "rb") as fh:
            logo64 = base64.b64encode(fh.read()).decode()
        st.markdown(f"""
        <div class="auth-hero">
          <img src="data:image/png;base64,{logo64}" alt="Cooler City" style="width:min(100%,360px);height:auto">
          <h2>Pantau penjualan, capai target, temukan paket terbaik.</h2>
          <p>Dashboard business intelligence berbasis data warehouse (star schema) dan algoritma Apriori.</p>
          <ul>
            <li>Ringkasan KPI lengkap dengan status target</li>
            <li>Analisis tren, jam ramai, kanal, dan kategori</li>
            <li>Market basket analysis &amp; rekomendasi bundling</li>
          </ul>
        </div>""", unsafe_allow_html=True)
    with right:
        ready = data.db_ready()
        tab_login, tab_signup = st.tabs(["Masuk", "Daftar akun"])
        with tab_login:
            st.markdown("#### Selamat datang kembali 👋")
            st.caption("Masuk dengan akun yang sudah disetujui Admin.")
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Masuk", type="primary", width="stretch")
            if submitted:
                if st.session_state.get("env_fail", 0) >= auth.MAX_ATTEMPTS:
                    st.error("Terlalu banyak percobaan gagal di sesi ini. Muat ulang halaman dan coba lagi nanti.")
                else:
                    conn = None
                    try:
                        if ready:
                            conn = data.db.connect()
                        user, msg = auth.login(conn, username, password)
                    finally:
                        if conn is not None:
                            conn.close()
                    if user:
                        st.session_state.update(user=user, env_fail=0)
                        st.rerun()
                    st.session_state["env_fail"] = st.session_state.get("env_fail", 0) + 1
                    st.error(msg)
            if not auth.env_admin():
                st.info("Akun Admin bawaan belum dibuat. Jalankan `python setup_login.py` lalu restart aplikasi.")
        with tab_signup:
            st.markdown("#### Ajukan akses")
            st.caption("Akun baru berperan **Manajemen** (hanya melihat dashboard) dan aktif setelah disetujui Admin.")
            if not ready:
                st.warning("Pendaftaran butuh koneksi database. Periksa SQL Server dan `.env`.")
            else:
                with st.form("signup_form", clear_on_submit=False):
                    full_name = st.text_input("Nama lengkap")
                    email = st.text_input("Email (opsional)")
                    new_user = st.text_input("Username", help="4–30 karakter: huruf, angka, titik, atau garis bawah.")
                    c1, c2 = st.columns(2)
                    pw = c1.text_input("Password", type="password", help="Minimal 8 karakter, berisi huruf dan angka.")
                    pw2 = c2.text_input("Ulangi password", type="password")
                    sent = st.form_submit_button("Kirim pendaftaran", type="primary", width="stretch")
                if sent:
                    with data.connection() as conn:
                        ok, msg = auth.register(conn, new_user, full_name, email, pw, pw2)
                    (st.success if ok else st.error)(msg)
        if not ready:
            with st.expander("Database belum tersambung"):
                st.code(st.session_state.get("db_error", ""))


user = st.session_state.get("user")
if not user:
    auth_screen()
    st.stop()

is_admin = user["role"] == "Admin"
data.db_ready()

def has_data():
    try:
        return not data.warehouse().empty
    except Exception:  # noqa: BLE001
        return False


data_ready = has_data()
pages = {}
if is_admin:
    # Kelola Data di paling atas: data harus di-upload lewat ETL sebelum dashboard terisi.
    pages["Kelola Data"] = [
        st.Page(etl_view.render, title="ETL & Data Warehouse", icon=":material/database_upload:", url_path="etl",
                default=not data_ready),
        st.Page(targets_view.render, title="Target KPI", icon=":material/flag:", url_path="target"),
        st.Page(users_view.render, title="Pengguna", icon=":material/group:", url_path="pengguna"),
    ]
pages["Dashboard"] = [
    st.Page(overview.render, title="Ringkasan KPI", icon=":material/space_dashboard:", url_path="ringkasan",
            default=data_ready or not is_admin),
    st.Page(sales.render, title="Analisis Penjualan", icon=":material/monitoring:", url_path="penjualan"),
]
pages["Market Basket"] = [
    st.Page(basket.render, title="Analisis Apriori", icon=":material/hub:", url_path="apriori"),
    st.Page(bundling.render, title="Rekomendasi Bundling", icon=":material/redeem:", url_path="bundling"),
]
pages["Akun"] = [st.Page(account.render, title="Akun Saya", icon=":material/person:", url_path="akun")]

st.logo(os.path.join(ASSETS, "logo.png"), size="large", icon_image=os.path.join(ASSETS, "icon.png"))
nav = st.navigation(pages)

with st.sidebar:
    role_color = "#0098C8" if is_admin else "#00568E"
    st.markdown(f'<div style="background:#F5FAFD;border:1px solid #E8EDF3;border-radius:14px;padding:10px 12px">'
                f'<div style="font-weight:700;color:#0B2D4F">{ui.html.escape(user["full_name"])}</div>'
                f'<div style="font-size:.8rem;color:#5F7189">@{ui.html.escape(user["username"])} · '
                f'<span style="color:{role_color};font-weight:700">{user["role"]}</span></div></div>', unsafe_allow_html=True)
    if st.button("Keluar", icon=":material/logout:", width="stretch"):
        st.session_state.clear()
        st.rerun()
    st.caption(f"SQL Server: {os.getenv('SQL_SERVER', 'localhost')} / {os.getenv('SQL_DATABASE', 'dw_coolercity')}")

nav.run()
