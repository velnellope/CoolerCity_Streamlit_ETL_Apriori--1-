"""Autentikasi: hash password PBKDF2, login dengan penguncian sementara, pendaftaran dengan persetujuan Admin."""
import base64
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta

import pandas as pd

import db

ITERATIONS = 260_000
ROLES = ["Admin", "Manajemen"]
MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


def make_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        method, iterations, salt, expected = encoded.split("$")
        if method != "pbkdf2_sha256" or not (100_000 <= int(iterations) <= 1_000_000):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError, AttributeError):
        return False


def password_problem(password: str, confirm: str | None = None):
    if len(password) < 8:
        return "Password minimal 8 karakter."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password harus berisi huruf dan angka."
    if confirm is not None and password != confirm:
        return "Konfirmasi password tidak sama."
    return None


def username_problem(username: str):
    if not re.fullmatch(r"[A-Za-z0-9_.]{4,30}", username or ""):
        return "Username 4–30 karakter, hanya huruf, angka, titik, atau garis bawah."
    return None


def env_admin():
    """Akun Admin bawaan dari .env (dibuat dengan setup_login.py). Tetap bisa dipakai walau tabel pengguna kosong."""
    u, h = os.getenv("APP_USERNAME", ""), os.getenv("APP_PASSWORD_HASH", "")
    return (u, h) if u and h else None


def login(conn, username: str, password: str):
    """Kembalikan (user_dict | None, pesan)."""
    username = (username or "").strip()
    builtin = env_admin()
    if builtin and hmac.compare_digest(username.lower(), builtin[0].lower()):
        if verify_password(password, builtin[1]):
            return {"username": builtin[0], "full_name": "Administrator", "role": "Admin", "builtin": True}, "ok"
        return None, "Username atau password salah."
    if conn is None:
        return None, "Database tidak tersambung; hanya akun Admin bawaan (.env) yang bisa login."
    user = db.get_user(conn, username)
    if user is None:
        verify_password(password, make_hash("dummy-password-1"))  # samakan waktu respons
        return None, "Username atau password salah."
    locked = pd.to_datetime(user.get("locked_until")) if user.get("locked_until") else None
    now = datetime.now()
    if locked is not None and pd.notna(locked) and locked > now:
        menit = max(1, int((locked - now).total_seconds() // 60) + 1)
        return None, f"Akun dikunci sementara karena terlalu banyak percobaan gagal. Coba lagi dalam {menit} menit."
    if not verify_password(password, user["password_hash"]):
        fails = int(user.get("failed_attempts") or 0) + 1
        if fails >= MAX_ATTEMPTS:
            db.update_user(conn, user["username"], failed_attempts=0,
                           locked_until=(now + timedelta(minutes=LOCK_MINUTES)).replace(microsecond=0))
            return None, f"Password salah {MAX_ATTEMPTS} kali. Akun dikunci {LOCK_MINUTES} menit."
        db.update_user(conn, user["username"], failed_attempts=fails)
        return None, f"Username atau password salah. Sisa percobaan: {MAX_ATTEMPTS - fails}."
    status = user["status"]
    if status == "pending":
        return None, "Akun Anda masih menunggu persetujuan Admin."
    if status == "rejected":
        return None, "Pendaftaran akun Anda ditolak. Hubungi Admin."
    if status != "active":
        return None, "Akun Anda dinonaktifkan. Hubungi Admin."
    db.update_user(conn, user["username"], failed_attempts=0, locked_until=None, last_login=now.replace(microsecond=0))
    return {"username": user["username"], "full_name": user["full_name"], "role": user["role"], "builtin": False}, "ok"


def register(conn, username, full_name, email, password, confirm):
    """Pendaftaran mandiri: akun dibuat berstatus 'pending' dan baru aktif setelah disetujui Admin."""
    for problem in (username_problem(username), password_problem(password, confirm)):
        if problem:
            return False, problem
    if len((full_name or "").strip()) < 3:
        return False, "Nama lengkap wajib diisi."
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "Format email tidak valid."
    builtin = env_admin()
    if (builtin and username.lower() == builtin[0].lower()) or db.get_user(conn, username):
        return False, "Username sudah dipakai."
    db.create_user(conn, username.strip(), full_name.strip(), (email or "").strip() or None, make_hash(password),
                   "Manajemen", "pending")
    return True, "Pendaftaran terkirim. Akun aktif setelah disetujui Admin."
