import io, ast, os, re, shutil, subprocess, sys

def rd(p): return io.open(p, encoding='utf-8').read()
def wr(p, s): io.open(p, 'w', encoding='utf-8', newline='\n').write(s)

SSL_BLOCK = '''# --- SSL-фикс (ТСПУ) inline ---
import os as _os_ssl
try:
    import certifi as _certifi_mod
    _os_ssl.environ["SSL_CERT_FILE"] = _certifi_mod.where()
    _os_ssl.environ["REQUESTS_CA_BUNDLE"] = _certifi_mod.where()
except Exception:
    pass
try:
    import urllib3 as _urllib3_ssl
    _urllib3_ssl.disable_warnings()
    import requests as _requests_ssl
    _me = _requests_ssl.Session.merge_environment_settings
    def _me_patch(self, url, proxies, stream, verify, cert):
        st = _me(self, url, proxies, stream, verify, cert)
        st["verify"] = False
        return st
    _requests_ssl.Session.merge_environment_settings = _me_patch
    _rq = _requests_ssl.Session.request
    def _rq_patch(self, *a, **k):
        k["verify"] = False
        return _rq(self, *a, **k)
    _requests_ssl.Session.request = _rq_patch
except Exception:
    pass
# --- конец SSL-фикса ---
'''

# 1) Чиним исходники
for f in ['tender_auto.py', 'sampler.py']:
    s = rd(f)
    if 'конец SSL-фикса' not in s:
        if re.search(r'(?m)^import patch_ssl[^\n]*\n', s):
            s = re.sub(r'(?m)^import patch_ssl[^\n]*\n', SSL_BLOCK, s, count=1)
        else:
            s = re.sub(r'(?m)^(import [^\n]+\n)', SSL_BLOCK + r'\1', s, count=1)
    old_base = "    _FROZEN_BASE = Path(_sysf.executable).resolve().parent"
    if old_base in s and 'config").exists()' not in s:
        s = s.replace(old_base, old_base +
            '\n    if not (_FROZEN_BASE / "config").exists() and (_FROZEN_BASE.parent / "config").exists():' +
            '\n        _FROZEN_BASE = _FROZEN_BASE.parent', 1)
    ast.parse(s); wr(f, s)
    print(f'✅ {f}: SSL inline + умный BASE')

s = rd('gui.py')
old_exe = '            exe = Path(sys.executable).resolve().parent / (Path(args[0]).stem + ".exe")'
if '"sampler": "sampler"' not in s and old_exe in s:
    s = s.replace(old_exe,
        '            stem = Path(args[0]).stem\n'
        '            sub = {"tender_auto": "engine", "sampler": "sampler"}.get(stem, "")\n'
        '            exe = Path(sys.executable).resolve().parent / sub / (stem + ".exe")', 1)
    ast.parse(s); wr('gui.py', s)
    print('✅ gui.py: движки ищутся в engine\\ и sampler\\')

# 2) Пересборка
print('🔨 Сборка PyInstaller (≈5-8 минут)...')
r = subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', 'build_all.spec'])
if r.returncode != 0:
    print('❌ сборка упала'); sys.exit(1)

# 3) Продуктовая папка
T = os.path.join('dist', 'TenderAuto')
if os.path.exists(T): shutil.rmtree(T)
shutil.copytree(os.path.join('dist', 'app_gui'), T)
shutil.copytree(os.path.join('dist', 'app_engine'), os.path.join(T, 'engine'))
shutil.copytree(os.path.join('dist', 'app_sampler'), os.path.join(T, 'sampler'))
for d in ['templates', 'config', 'license']:
    if os.path.exists(d): shutil.copytree(d, os.path.join(T, d), dirs_exist_ok=True)
for f in ['brands_extra.txt', 'secrets.txt', 'sampler_config.txt']:
    if os.path.exists(f): shutil.copy2(f, T)

print('✅ Готово. Структура:')
for root, dirs, files in os.walk(T):
    lvl = root.replace(T, '').count(os.sep)
    if lvl < 2:
        print('   ' * lvl + os.path.basename(root) + '/')
        if lvl == 0:
            for f in files: print('   ' + f)
print('\n▶ Запускай: dist\\TenderAuto\\TenderAuto.exe')