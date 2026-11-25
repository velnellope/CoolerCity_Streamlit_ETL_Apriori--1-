"""Create local login credentials without printing/storing plaintext passwords."""
import getpass
from pathlib import Path
from auth import make_hash

path = Path(__file__).resolve().parent / '.env'
existing = path.read_text(encoding='utf-8') if path.exists() else (Path(__file__).resolve().parent / '.env.example').read_text(encoding='utf-8')
username = input('Username login: ').strip()
password = getpass.getpass('Password (min 10 karakter): ')
confirmation = getpass.getpass('Ulangi password: ')
if not username or len(password) < 10 or password != confirmation:
    raise SystemExit('Gagal: username harus diisi, password minimal 10 karakter, dan kedua password harus sama.')
values = {'APP_USERNAME': username, 'APP_PASSWORD_HASH': make_hash(password)}
lines = [line for line in existing.splitlines() if not any(line.startswith(key+'=') for key in values)]
lines.extend(f'{key}={value}' for key,value in values.items())
path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
print('Login disimpan ke .env. Jalankan: streamlit run app.py')
