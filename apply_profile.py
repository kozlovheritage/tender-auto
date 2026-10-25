# apply_profile.py <имя> — разворачивает профиль в рабочие файлы корня
import sys, shutil, pathlib
B = pathlib.Path(__file__).resolve().parent
if len(sys.argv) != 2:
    print("Использование: python apply_profile.py <имя_профиля>"); sys.exit(1)
name = sys.argv[1]
prof = B / "profiles" / name
if not prof.is_dir():
    print("Профиль не найден:", prof); sys.exit(1)

files = {  # источник в профиле -> рабочий файл в корне
    "stop_factors.txt":      B / "config" / "stop_factors.txt",
    "sampler_config.txt":     B / "sampler_config.txt",
    "sender_config.json":     B / "sender_config.json",
    "secrets.txt":            B / "secrets.txt",
    "brands_extra.txt":       B / "brands_extra.txt",
}
done, missing = [], []
for rel, dst in files.items():
    src = prof / rel
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst); done.append(rel)
    elif rel not in ("brands_extra.txt",):  # brands_extra есть не у всех клиентов
        if rel in ("sender_config.json", "secrets.txt", "sampler_config.txt") and name.lower() == "cemtorg":
            pass  # cemtorg не требует письмные файлы
        else:
            missing.append(rel)
tdir = B / "templates"
tdir.mkdir(exist_ok=True)
n = 0
for t in (prof / "templates").glob("*"):
    if t.is_file():
        shutil.copy2(t, tdir / t.name); n += 1

    (B / "config" / "active_profile.txt").write_text(name, encoding="utf-8")
print(f"Профиль '{name}' применён: {', '.join(done)}" + (f", шаблонов: {n}" if n else ""))
if missing:
    print("В профиле не хватает:", ", ".join(missing))
# >>> ACTIVE-PROFILE-WRITE >>>
import pathlib as _pl_ap, sys as _sys_ap
_prof_ap = _sys_ap.argv[1].strip().lower() if len(_sys_ap.argv) > 1 and not _sys_ap.argv[1].startswith('-') else ''
if _prof_ap:
    _p_ap = _pl_ap.Path(__file__).resolve().parent / 'config' / 'active_profile.txt'
    _p_ap.parent.mkdir(parents=True, exist_ok=True)
    _p_ap.write_text(_prof_ap, encoding='utf-8')
    print(f'[apply_profile] config/active_profile.txt = {_prof_ap}')
# <<< ACTIVE-PROFILE-WRITE <<<
