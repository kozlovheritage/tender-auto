# assemble_product.py v2 — не зависит от имён внутренних папок PyInstaller
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "dist"
OUT = DIST / "TenderAuto"

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)

def cf(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.exists():
        print("  ⚠️ нет:", src.relative_to(BASE)); return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("  ✔", dst.relative_to(OUT))
    return True

def component(collect: Path, out_dir: Path, exe_name: str):
    """Копирует ВСЁ содержимое COLLECT-папки, кроме exe (exe кладём отдельно)."""
    if not collect.exists():
        print("  ⚠️ нет COLLECT:", collect.relative_to(BASE)); return
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for item in collect.iterdir():
        if item.name.lower() == exe_name.lower():
            continue
        dst = out_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)
        n += 1
    print(f"  ✔ {collect.name} → {out_dir.relative_to(OUT)} ({n} объектов)")

print("Сборка dist/TenderAuto ...")
# GUI: exe в корень поставки, содержимое рядом
cf(DIST/"app_gui"/"TenderAuto.exe", OUT/"TenderAuto.exe")
component(DIST/"app_gui", OUT, "TenderAuto.exe")
# ENGINE: exe в engine/, содержимое рядом с ним
cf(DIST/"app_engine"/"tender_auto.exe", OUT/"engine"/"tender_auto.exe")
component(DIST/"app_engine", OUT/"engine", "tender_auto.exe")
# SAMPLER: exe в sampler/, содержимое рядом
cf(DIST/"app_sampler"/"sampler.exe", OUT/"sampler"/"sampler.exe")
component(DIST/"app_sampler", OUT/"sampler", "sampler.exe")

# Конфиги и ресурсы
ct_src = BASE/"config"
if ct_src.exists():
    shutil.copytree(ct_src, OUT/"config", dirs_exist_ok=True)
    print("  ✔ папка: config")
shutil.copytree(BASE/"templates", OUT/"templates", dirs_exist_ok=True)
print("  ✔ папка: templates")
cf(BASE/"sender_config.json", OUT/"config"/"sender_config.json")
for f in ("secrets.txt", "sender_config.json", "brands_extra.txt",
          "sampler_config.txt", "ui_theme.txt"):
    cf(BASE/f, OUT/f)

(OUT/"license").mkdir(exist_ok=True)
(OUT/"data").mkdir(exist_ok=True)
(OUT/"output").mkdir(exist_ok=True)
print("\n✅ Продуктовая папка готова: dist/TenderAuto")