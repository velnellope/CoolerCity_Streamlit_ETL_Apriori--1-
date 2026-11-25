import streamlit as st

import auth
import data
import db
import ui


def render():
    user = st.session_state["user"]
    ui.page_header("Akun", "Akun Saya", "Informasi akun dan penggantian password.")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Nama", user["full_name"])
        c2.metric("Username", "@" + user["username"])
        c3.metric("Peran", user["role"])
        st.caption("Admin: semua menu termasuk ETL, Target KPI, dan Pengguna. Manajemen: menu Dashboard & Market Basket.")
    if user.get("builtin"):
        st.info("Ini akun Admin bawaan dari `.env`. Untuk mengganti password-nya, jalankan ulang `python setup_login.py` "
                "lalu restart aplikasi.")
        return
    with st.container(border=True):
        st.markdown("**Ganti password**")
        with st.form("chg_pw", clear_on_submit=True):
            old = st.text_input("Password lama", type="password")
            c1, c2 = st.columns(2)
            new = c1.text_input("Password baru", type="password", help="Minimal 8 karakter, berisi huruf dan angka.")
            new2 = c2.text_input("Ulangi password baru", type="password")
            ok = st.form_submit_button("Simpan password", type="primary")
        if ok:
            with data.connection() as conn:
                row = db.get_user(conn, user["username"])
                if not row or not auth.verify_password(old, row["password_hash"]):
                    st.error("Password lama salah.")
                    return
                problem = auth.password_problem(new, new2)
                if problem:
                    st.error(problem)
                    return
                db.update_user(conn, user["username"], password_hash=auth.make_hash(new))
            st.success("Password berhasil diganti.")
