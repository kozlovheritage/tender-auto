# safe_rebuild.py — обёртка: убивает блокирующие процессы, чистит temp_files, потом зовёт make_product_v2.py
import os, subprocess, sys, stat, gc, time

def force_rmtree(path):
    if not os.path.exists(path):
        return
    gc.collect()
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            for _ in range(3):
                try:
                    os.chmod(fp, stat.S_IWRITE)
                    os.unlink(fp)
                    break
                except Exception:
                    time.sleep(0.3)
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except Exception:
                pass
    try:
        os.rmdir(path)
    except Exception:
        pass

print("🔪 Закрываю процессы, которые могут держать файлы...")
subprocess.run('taskkill /F /IM WINWORD.EXE /IM ACRORD32.EXE /IM Acrobat.exe '
               '/IM TenderAuto.exe /IM tender_auto.exe /IM sampler.exe',
               shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

print("🧹 Чищу temp_files во всех сборках...")
for root, dirs, files in os.walk("."):
    if os.path.basename(root) == "temp_files":
        force_rmtree(root)
        os.makedirs(root, exist_ok=True)

print("🚀 Запускаю make_product_v2.py...")
r = subprocess.run([sys.executable, "make_product_v2.py"])
if r.returncode != 0:
    print(f"⚠️ make_product_v2.py вернул код {r.returncode} — если снова PermissionError, "
          f"пришли traceback, разберу предметно.")
else:
    print("✅ Пересборка прошла без PermissionError.")