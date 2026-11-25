import pandas as pd
import streamlit as st

import auth
import data
import db
import ui

STATUS_LABEL = {"pending": "⏳ Menunggu", "active": "✅ Aktif", "rejected": "❌ Ditolak", "inactive": "⏸️ Nonaktif"}


def render():
    ui.page_header("Kelola Data", "Pengguna",
                   "Setujui pendaftaran, atur peran, dan nonaktifkan akun. Admin = akses penuh; Manajemen = lihat dashboard.")
    me = st.session_state["user"]["username"]
    try:
        with data.connection() as conn:
            users = db.list_users(conn)
    except Exception as exc:  # noqa: BLE001
        st.error("Database belum tersambung.")
        st.code(str(exc))
        return
    pending = users[users.status == "pending"]
    a, b, c = st.columns(3)
    a.metric("Menunggu persetujuan", len(pending))
    b.metric("Pengguna aktif", int((users.status == "active").sum()))
    c.metric("Admin aktif", int(((users.status == "active") & (users.role == "Admin")).sum()) + (1 if auth.env_admin() else 0),
             help="Termasuk akun Admin bawaan dari .env.")

    ui.section("Permintaan akses", "Pendaftaran baru dari halaman login.")
    if pending.empty:
        st.caption("Tidak ada permintaan baru.")
    for r in pending.itertuples():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2.2, 1.2, 1, 1])
            c1.markdown(f"**{r.full_name}** · @{r.username}  \n<span style='color:#5F7189;font-size:.85rem'>"
                        f"{r.email or 'tanpa email'} · daftar {pd.to_datetime(r.created_at):%d %b %Y %H:%M}</span>",
                        unsafe_allow_html=True)
            role = c2.selectbox("Peran", auth.ROLES, index=1, key=f"role_{r.username}", label_visibility="collapsed")
            if c3.button("Setujui", key=f"ok_{r.username}", type="primary", icon=":material/check:", width="stretch"):
                with data.connection() as conn:
                    db.update_user(conn, r.username, status="active", role=role, approved_by=me)
                st.toast(f"{r.username} disetujui sebagai {role}.")
                st.rerun()
            if c4.button("Tolak", key=f"no_{r.username}", icon=":material/close:", width="stretch"):
                with data.connection() as conn:
                    db.update_user(conn, r.username, status="rejected", approved_by=me)
                st.rerun()

    ui.section("Semua pengguna")
    if auth.env_admin():
        st.caption(f"Akun Admin bawaan **@{auth.env_admin()[0]}** dikelola lewat `.env` (`setup_login.py`) dan tidak tampil di sini.")
    if users.empty:
        st.caption("Belum ada pengguna terdaftar.")
        return
    show = users.assign(Status=users.status.map(STATUS_LABEL),
                        Login_terakhir=pd.to_datetime(users.last_login).dt.strftime("%d %b %Y %H:%M").fillna("–"))
    st.dataframe(show[["username", "full_name", "email", "role", "Status", "Login_terakhir", "approved_by"]]
                 .rename(columns={"username": "Username", "full_name": "Nama", "email": "Email", "role": "Peran",
                                  "Login_terakhir": "Login terakhir", "approved_by": "Disetujui oleh"}),
                 hide_index=True, width="stretch")

    with st.container(border=True):
        st.markdown("**Ubah akun**")
        target = st.selectbox("Pilih pengguna", users.username.tolist(), key="usr_pick")
        row = users[users.username == target].iloc[0]
        c1, c2 = st.columns(2)
        new_role = c1.selectbox("Peran", auth.ROLES, index=auth.ROLES.index(row.role), key="usr_role")
        statuses = ["active", "inactive", "pending", "rejected"]
        new_status = c2.selectbox("Status", statuses, index=statuses.index(row.status), format_func=STATUS_LABEL.get,
                                  key="usr_status")
        new_pw = st.text_input("Reset password (kosongkan jika tidak diubah)", type="password", key="usr_pw",
                               help="Berikan password sementara ini ke pengguna, lalu minta ia menggantinya di Akun Saya.")
        if st.button("Simpan perubahan", type="primary", icon=":material/save:"):
            if target.lower() == me.lower() and (new_role != "Admin" or new_status != "active"):
                st.error("Anda tidak bisa menurunkan peran atau menonaktifkan akun sendiri.")
                return
            with data.connection() as conn:
                demoting = row.role == "Admin" and row.status == "active" and (new_role != "Admin" or new_status != "active")
                if demoting and db.count_active_admins(conn) <= 1 and not auth.env_admin():
                    st.error("Harus ada minimal satu Admin aktif.")
                    return
                fields = dict(role=new_role, status=new_status)
                if new_pw:
                    problem = auth.password_problem(new_pw)
                    if problem:
                        st.error(problem)
                        return
                    fields.update(password_hash=auth.make_hash(new_pw), failed_attempts=0, locked_until=None)
                db.update_user(conn, target, **fields)
            st.success("Perubahan tersimpan.")
            st.rerun()
