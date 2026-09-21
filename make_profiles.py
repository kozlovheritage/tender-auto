# make_profiles.py — разово: структура profiles/ + перенос конфигов + снос dist
import json, shutil, pathlib

B = pathlib.Path(__file__).resolve().parent
P = B / "profiles"
for d in ("vitro/templates", "cemtorg", "owner"):
    (P / d).mkdir(parents=True, exist_ok=True)

# 1) vitro = слепок доставленной сборки
src = B / "dist" / "TenderAuto"
if src.exists():
    for f in ("stop_factors.txt", "sender_config.json", "settings.toml"):
        s = src / "config" / f
        if s.exists(): shutil.copy2(s, P / "vitro" / f)
    for f in ("sampler_config.txt", "ui_theme.txt", "secrets.txt"):
        s = src / f
        if s.exists(): shutil.copy2(s, P / "vitro" / f)
    k = src / "license" / "key.txt"
    if k.exists(): shutil.copy2(k, P / "vitro" / "key.txt")
    for t in (src / "templates").glob("*.txt"):
        shutil.copy2(t, P / "vitro" / "templates" / t.name)
    print("vitro: слепок доставленной сборки собран")

# 2) owner = твой текущий рабочий конфиг из корня
for f in ("secrets.txt", "sender_config.json", "sampler_config.txt", "ui_theme.txt"):
    s = B / f
    if s.exists(): shutil.copy2(s, P / "owner" / f)
for f in ("stop_factors.txt", "settings.toml"):
    s = B / "config" / f
    if s.exists(): shutil.copy2(s, P / "owner" / f)
print("owner: слепок рабочего конфига собран")

# 3) cemtorg — заготовка
CEM = P / "cemtorg"
(CEM / "profile.json").write_text(json.dumps({
    "profile": "cemtorg",
    "display_name": "Cemtorg",
    "catalog_mode": True,
    "rfq_enabled": False,
    "suppliers_in_report": False,
    "china_check": False,
    "min_delivery_days": 15,
    "regions_whitelist": ["Москва", "Московская область", "Санкт-Петербург",
                          "Ленинградская область", "Смоленская область",
                          "Пензенская область", "Казань", "Республика Татарстан"],
}, ensure_ascii=False, indent=2), encoding="utf-8")
(CEM / "stop_factors.txt").write_text(
    "# Стоп-факторы Цемторг\n"
    "# Единственный жёсткий стоп: слишком короткий срок поставки.\n"
    "Срок поставки менее 15 календарных дней\n", encoding="utf-8")
(CEM / "README.md").write_text(
    "# Профиль Цемторг\n\n"
    "- Каталог: catalog.json — TODO собрать с cemtorg.ooo (все товарные позиции с характеристиками)\n"
    "- Логика: позиция в каталоге → участвуем; похожее → уточнение; иное → не участвуем\n"
    "- RFQ-рассылка: отключена\n- Поставщики в отчёте: отключены\n- Китай: не проверяем\n"
    "- Регионы: МСК, МО, СПб, Смоленск, Пенза, Казань\n", encoding="utf-8")
print("cemtorg: заготовка создана")

# 4) dist сносим целиком: всё ценное уже скопировано, остальное пересоздаётся сборкой
if (B / "dist").exists():
    shutil.rmtree(B / "dist")
    print("dist/ удалён")

# 5) .gitignore: секреты и ключи профилей не коммитим
gi = B / ".gitignore"
t = gi.read_text(encoding="utf-8")
add = ""
for rule in ("profiles/*/secrets.txt", "profiles/*/key.txt"):
    if rule not in t:
        add += f"\n{rule}\n"
if add:
    gi.write_text(t.rstrip() + add + "\n", encoding="utf-8")
    print(".gitignore обновлён")

print("\nИтог:")
for p in sorted(P.rglob("*")):
    if p.is_file():
        print("  ", p.relative_to(B))